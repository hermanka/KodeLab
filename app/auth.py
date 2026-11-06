import hashlib
import os
import re
import secrets
from datetime import timedelta
from typing import Literal

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import Field, SecretStr, field_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contracts import StrictModel
from app.db import get_db, session
from app.models import AuditEvent, AuthSession, RateBucket, User, utcnow

router = APIRouter(tags=["accounts"])
bearer = HTTPBearer(auto_error=False)
hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
dummy_hash = hasher.hash(secrets.token_urlsafe(32))
COOKIE = "judgement_session"
CSRF_COOKIE = "judgement_csrf"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def audit(db, actor, action, object_id, **details):
    db.add(AuditEvent(actor_id=actor.id if actor else None, action=action,
                      object_id=object_id, details=details))


class Credentials(StrictModel):
    username: str = Field(min_length=3, max_length=40)
    password: SecretStr = Field(min_length=15, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,39}", value):
            raise ValueError("Use 3-40 lowercase letters, digits or underscores; start with a letter")
        return value


class CreateUser(Credentials):
    role: Literal["student", "teacher", "admin"] = "student"
    full_name: str = Field(default="", max_length=120)
    email: str | None = Field(default=None, max_length=254)

    @field_validator("email")
    @classmethod
    def email_format(cls, value):
        return normalized_email(value) if value else None


def normalized_email(value):
    value = value.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value) or len(value) > 254:
        raise ValueError("Supply a valid email address")
    return value


class Registration(Credentials):
    full_name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)

    @field_validator("full_name")
    @classmethod
    def name(cls, value):
        if not value.strip():
            raise ValueError("Full name is required")
        return value.strip()

    @field_validator("email")
    @classmethod
    def email_format(cls, value):
        return normalized_email(value)


class ProfileUpdate(StrictModel):
    full_name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)

    @field_validator("full_name")
    @classmethod
    def name(cls, value):
        return Registration.name(value)

    @field_validator("email")
    @classmethod
    def email_format(cls, value):
        return normalized_email(value)


class PasswordUpdate(StrictModel):
    current_password: SecretStr = Field(min_length=1, max_length=128)
    new_password: SecretStr = Field(min_length=15, max_length=128)


class UpdateUser(StrictModel):
    role: Literal["student", "teacher", "admin"] | None = None
    is_active: bool | None = None


def user_view(user):
    return {"id": user.id, "username": user.username, "full_name": user.full_name,
            "email": user.email, "role": user.role, "is_active": user.is_active}


def check_origin(request):
    origin = request.headers.get("origin")
    allowed = {value.strip() for value in os.getenv(
        "APP_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000",
    ).split(",")}
    if origin and origin not in allowed:
        raise HTTPException(403, "Origin not allowed")


def consume_rate(key, limit, seconds, *, increment=True):
    """Persistent, transactionally locked buckets; do not roll back failed login counters."""
    key = digest(key)
    for _ in range(3):
        try:
            with session() as db, db.begin():
                row = db.scalar(select(RateBucket).where(RateBucket.key == key).with_for_update())
                now = utcnow()
                if not row and increment:
                    db.add(RateBucket(key=key, window_start=now, count=1))
                elif row:
                    if row.window_start + timedelta(seconds=seconds) <= now:
                        row.window_start, row.count = now, 0
                    if row.count >= limit:
                        raise HTTPException(429, "Rate limit exceeded", headers={"Retry-After": str(seconds)})
                    row.count += int(increment)
            return
        except IntegrityError:
            continue
    raise HTTPException(503, "Rate limiter unavailable")


def current_user(request: Request, credentials: HTTPAuthorizationCredentials | None = Security(bearer),
                 db: Session = Depends(get_db)):
    cookie_auth = credentials is None
    token = credentials.credentials if credentials else request.cookies.get(COOKIE)
    if not token or len(token) > 128:
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    auth_session = db.get(AuthSession, digest(token))
    now = utcnow()
    if not auth_session or auth_session.expires_at <= now or auth_session.last_seen + timedelta(minutes=30) <= now:
        raise HTTPException(401, "Session invalid or expired")
    user = db.get(User, auth_session.user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "Session invalid or expired")
    if cookie_auth and request.method not in ("GET", "HEAD", "OPTIONS"):
        check_origin(request)
        csrf = request.headers.get("x-csrf-token", "")
        if not secrets.compare_digest(digest(csrf), auth_session.csrf_hash):
            raise HTTPException(403, "CSRF token required")
    request.state.session_hash = auth_session.token_hash
    auth_session.last_seen = now
    db.commit()
    return user


def administrator(user: User = Depends(current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Administrator access required")
    return user


def create_user(db, data, actor=None):
    user = User(username=data.username, password_hash=hasher.hash(data.password.get_secret_value()),
                role=getattr(data, "role", "student"), full_name=getattr(data, "full_name", "").strip(),
                email=normalized_email(data.email) if getattr(data, "email", None) else None)
    db.add(user)
    try:
        db.flush()
        audit(db, actor or user, "account.created", user.id, role=user.role)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Account cannot be created")
    return user


@router.post("/auth/register", status_code=201)
def register(data: Registration, request: Request, db: Session = Depends(get_db)):
    check_origin(request)
    consume_rate("register:" + request.client.host, 5, 3600)
    return user_view(create_user(db, data))


@router.post("/auth/login")
def login(data: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    check_origin(request)
    consume_rate("login-ip:" + request.client.host, 100, 300)
    consume_rate("login-user:" + data.username, 10, 300)
    user = db.scalar(select(User).where(User.username == data.username).with_for_update())
    try:
        hasher.verify(user.password_hash if user else dummy_hash, data.password.get_secret_value())
        valid = user is not None and user.is_active
    except (VerificationError, InvalidHashError):
        valid = False
    if not valid:
        raise HTTPException(401, "Invalid username or password")
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hasher.hash(data.password.get_secret_value())
    existing = db.scalars(select(AuthSession).where(AuthSession.user_id == user.id).order_by(AuthSession.created_at)).all()
    for old in existing[:max(0, len(existing) - 4)]:
        db.delete(old)
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(AuthSession(token_hash=digest(token), user_id=user.id, csrf_hash=digest(csrf),
                       expires_at=utcnow() + timedelta(hours=12)))
    audit(db, user, "session.created", user.id)
    db.commit()
    secure = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    response.set_cookie(COOKIE, token, httponly=True, secure=secure, samesite="lax", max_age=43200)
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, secure=secure, samesite="lax", max_age=43200)
    response.headers["Cache-Control"] = "no-store"
    return {"access_token": token, "token_type": "bearer", "csrf_token": csrf, "user": user_view(user)}


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return user_view(user)


@router.patch("/auth/profile")
def update_profile(data: ProfileUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    target = db.scalar(select(User).where(User.id == user.id).with_for_update())
    target.full_name, target.email = data.full_name, data.email
    try:
        audit(db, user, "account.profile_updated", user.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email is already in use")
    return user_view(target)


@router.post("/auth/password")
def change_password(data: PasswordUpdate, request: Request, response: Response,
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
    consume_rate("password:" + user.id, 5, 300)
    target = db.scalar(select(User).where(User.id == user.id).with_for_update().execution_options(populate_existing=True))
    try:
        hasher.verify(target.password_hash, data.current_password.get_secret_value())
    except (VerificationError, InvalidHashError):
        raise HTTPException(400, "Current password is incorrect")
    if data.current_password.get_secret_value() == data.new_password.get_secret_value():
        raise HTTPException(422, "New password must differ from current password")
    target.password_hash = hasher.hash(data.new_password.get_secret_value())
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    audit(db, user, "account.password_changed", user.id)
    db.commit()
    response.delete_cookie(COOKIE)
    response.delete_cookie(CSRF_COOKIE)
    return {"status": "password_changed", "login_required": True}


@router.post("/auth/logout")
def logout(request: Request, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.get(AuthSession, request.state.session_hash)
    db.delete(row)
    audit(db, user, "session.revoked", user.id)
    db.commit()
    response.delete_cookie(COOKIE)
    response.delete_cookie(CSRF_COOKIE)
    return {"status": "logged_out"}


@router.post("/admin/users", status_code=201)
def admin_create_user(data: CreateUser, user: User = Depends(administrator), db: Session = Depends(get_db)):
    return user_view(create_user(db, data, user))


@router.get("/admin/users")
def list_users(offset: int = 0, user: User = Depends(administrator), db: Session = Depends(get_db)):
    return [user_view(row) for row in db.scalars(select(User).order_by(User.created_at).offset(max(0, offset)).limit(100))]


@router.patch("/admin/users/{user_id}")
def update_user(user_id: str, data: UpdateUser, user: User = Depends(administrator), db: Session = Depends(get_db)):
    target = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if not target:
        raise HTTPException(404, "Account not found")
    if target.id == user.id:
        raise HTTPException(409, "Use another administrator to change your own role or active status")
    changes = data.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(422, "No changes supplied")
    for key, value in changes.items():
        setattr(target, key, value)
    db.execute(delete(AuthSession).where(AuthSession.user_id == target.id))
    audit(db, user, "account.permissions_changed", target.id, **changes)
    db.commit()
    return user_view(target)


@router.get("/admin/audit")
def audit_events(offset: int = 0, user: User = Depends(administrator), db: Session = Depends(get_db)):
    return [{"id": row.id, "actor_id": row.actor_id, "action": row.action, "object_id": row.object_id,
             "details": row.details, "created_at": row.created_at} for row in db.scalars(
                 select(AuditEvent).order_by(AuditEvent.created_at.desc()).offset(max(0, offset)).limit(100))]
