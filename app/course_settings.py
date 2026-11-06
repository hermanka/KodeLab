import hashlib
import hmac
import secrets
import base64
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet, InvalidToken

from app.auth import audit, consume_rate, current_user
from app.config import required_secret
from app.content import CourseInput
from app.contracts import StrictModel
from app.course_lifecycle import owned_course
from app.db import get_db
from app.models import Course, CourseMember, QuotaLock, User, utcnow

router = APIRouter(tags=["class settings and invitations"])


class SettingsInput(CourseInput):
    edit_revision: int = Field(ge=1)


class JoinInput(StrictModel):
    code: str = Field(pattern=r"^[0-9]{6}$")


def code_digest(code):
    return hmac.new(required_secret("CLASS_INVITE_SECRET").encode(), code.encode(), hashlib.sha256).hexdigest()


def code_cipher():
    key = hashlib.sha256(("invite-encryption:" + required_secret("CLASS_INVITE_SECRET")).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def settings_view(course):
    code = None
    if course.invite_ciphertext and course.invite_expires_at and course.invite_expires_at > utcnow() and not course.is_public and not course.archived:
        try:
            code = code_cipher().decrypt(course.invite_ciphertext.encode()).decode()
        except InvalidToken:
            pass
    return {"id": course.id, "title": course.title, "description": course.description, "code": code,
            "is_public": course.is_public, "archived": course.archived, "edit_revision": course.edit_revision,
            "invite_enabled": bool(course.invite_digest and course.invite_expires_at and course.invite_expires_at > utcnow() and not course.is_public and not course.archived),
            "invite_expires_at": course.invite_expires_at.isoformat() + "Z" if course.invite_expires_at else None}


def writable(course):
    if course.archived:
        raise HTTPException(409, "Class archived; restore it before making changes")


@router.get("/courses/{course_id}/settings")
def read_settings(course_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return settings_view(owned_course(db, user, course_id))


@router.patch("/courses/{course_id}/settings")
def update_settings(course_id: str, data: SettingsInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    course = owned_course(db, user, course_id)
    writable(course)
    if data.edit_revision != course.edit_revision:
        raise HTTPException(409, "Class settings changed; reload before saving")
    course.title, course.description, course.is_public = data.title, data.description, data.is_public
    course.edit_revision += 1
    if course.is_public:
        course.invite_digest, course.invite_expires_at = None, None
        course.invite_ciphertext = None
    audit(db, user, "course.settings_updated", course.id, is_public=course.is_public)
    db.commit()
    return settings_view(course)


@router.post("/courses/{course_id}/invitation")
def rotate_invitation(course_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    course = owned_course(db, user, course_id)
    writable(course)
    if course.is_public:
        raise HTTPException(409, "Invitation codes are only available for private classes")
    # owned_course locks admission, serializing rotation/join/delete and uniqueness checks.
    for _ in range(20):
        code = f"{secrets.randbelow(1_000_000):06d}"
        digest = code_digest(code)
        if digest != course.invite_digest and not db.scalar(select(Course.id).where(Course.invite_digest == digest)):
            break
    else:
        raise HTTPException(503, "Unable to generate an invitation code; try again")
    course.invite_digest, course.invite_expires_at = digest, utcnow() + timedelta(hours=24)
    course.invite_ciphertext = code_cipher().encrypt(code.encode()).decode()
    audit(db, user, "course.invitation_rotated", course.id)
    db.commit()
    # Settings can decrypt the code for the owner; lists and audit never include it.
    return {"code": code, "expires_at": course.invite_expires_at.isoformat() + "Z"}


@router.delete("/courses/{course_id}/invitation")
def revoke_invitation(course_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    course = owned_course(db, user, course_id)
    writable(course)
    course.invite_digest, course.invite_expires_at = None, None
    course.invite_ciphertext = None
    audit(db, user, "course.invitation_revoked", course.id)
    db.commit()
    return {"status": "revoked"}


@router.post("/courses/join")
def join_class(data: JoinInput, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    consume_rate("invite-user:" + user.id, 5, 300)
    db.scalar(select(QuotaLock).where(QuotaLock.id == "admission").with_for_update())
    ip_key = "invite-ip:" + (request.client.host if request.client else "unknown")
    consume_rate(ip_key, 30, 300, increment=False)
    course = db.scalar(select(Course).where(Course.invite_digest == code_digest(data.code),
        Course.invite_expires_at > utcnow(), Course.is_public.is_(False), Course.archived.is_(False)).with_for_update())
    if not course:
        consume_rate(ip_key, 30, 300)
        raise HTTPException(400, "Invalid or expired invitation code")
    membership = db.get(CourseMember, (course.id, user.id))
    if not membership:
        db.add(CourseMember(course_id=course.id, user_id=user.id, role="student", access_source="invite"))
        audit(db, user, "course.invitation_joined", course.id)
        db.flush()
        membership = db.get(CourseMember, (course.id, user.id))
    if membership.access_source == "public":
        membership.access_source = "invite"
        audit(db, user, "course.invitation_joined", course.id)
    elif membership.role != "teacher" and membership.access_source != "assignment":
        membership.access_source = "invite"
    db.commit()
    return {"course_id": course.id, "title": course.title, "status": "joined"}
