import hashlib
import json
import os
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import audit, current_user, router as auth_router
from app.body_limit import BodyLimitMiddleware
from app.contracts import ReplayInput, RunRequest, SubmitRequest
from app.db import get_db
from app.models import Attempt, Course, CourseMember, Problem, ProblemVersion, QuotaLock, Submission, User, utcnow
from app.content import course_access, is_instructor, problem_access, public_problem, router as content_router
from app.providers import ProviderUnavailable, available_providers, choose_provider, provider_for
from app.judge_plugins import router as plugins_router
from app.learning import authorize_step_submission, router as learning_router
from app.course_lifecycle import router as lifecycle_router
from app.course_settings import router as settings_router
from app.reports import router as reports_router

app = FastAPI(title="JudgementSystem C/C++", version="0.3.0",
              description="Akun, kelas, authoring materi/soal, publikasi berversi, dan judge C/C++ modular.")
app.add_middleware(BodyLimitMiddleware, max_bytes=2097152)
app.include_router(auth_router)
app.include_router(learning_router)
app.include_router(content_router)
app.include_router(lifecycle_router)
app.include_router(settings_router)
app.include_router(reports_router)
app.include_router(plugins_router)

WEB = Path(__file__).resolve().parent.parent / "web"
app.mount("/assets", StaticFiles(directory=str(WEB), check_dir=False), name="assets")


@app.get("/", include_in_schema=False)
def web_app():
    return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-store"})


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Pydantic's default errors echo submitted input, including passwords/source.
    return JSONResponse(status_code=422, content={"detail": [
        {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()]})


@app.exception_handler(ProviderUnavailable)
async def provider_unavailable(request: Request, exc: ProviderUnavailable):
    return JSONResponse(status_code=503, content={"detail": "Configured judging plugin unavailable"})


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if not request.url.path.startswith(("/docs", "/redoc")):
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health/live", tags=["health"])
def live():
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
def ready(db: Session = Depends(get_db)):
    from redis import Redis
    try:
        db.execute(text("SELECT 1"))
        Redis.from_url(os.environ["REDIS_URL"], socket_timeout=2).ping()
        if not provider_for("custom").health_check():
            raise RuntimeError("runner unavailable")
    except Exception:
        raise HTTPException(503, "Dependencies not ready")
    return {"status": "ready"}


@app.get("/providers")
def providers(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return available_providers(db)


@app.get("/problems")
def problems(offset: int = 0, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role == "student":
        return []  # Learner exercises are available exclusively inside an enrollment.
    query = select(ProblemVersion).outerjoin(Problem, ProblemVersion.problem_id == Problem.id).outerjoin(Course)
    allowed = True if user.role == "admin" else or_(Course.is_public.is_(True), Course.owner_id == user.id,
        Course.id.in_(select(CourseMember.course_id).where(CourseMember.user_id == user.id, CourseMember.access_source != "public")))
    query = query.where(ProblemVersion.status == "published", or_(ProblemVersion.problem_id.is_(None), and_(
        Problem.archived.is_(False), Problem.published_version_id == ProblemVersion.id, allowed)))
    return [public_problem(db, p) for p in db.scalars(query.order_by(ProblemVersion.id).offset(max(0, offset)).limit(100))]


@app.get("/problems/{version_id}")
def read_problem(version_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    version = db.get(ProblemVersion, version_id)
    problem_access(db, user, version)
    return public_problem(db, version)


def serialize_submission(submission, attempt, include_source=False):
    result = {"id": submission.id, "owner_id": submission.owner_id, "attempt_id": attempt.id, "mode": submission.mode,
            "enrollment_id": submission.enrollment_id, "path_step_id": submission.path_step_id,
            "language": submission.language, "problem_version_id": submission.problem_version_id,
            "provider": attempt.provider, "provider_revision": attempt.snapshot.get("provider_revision"),
            "state": attempt.state, "verdict": attempt.verdict,
            "score": attempt.score, "result": attempt.result, "error_code": attempt.error_code,
            "created_at": submission.created_at.isoformat() + "Z"}
    if include_source:
        result["source"] = submission.source
    return result


def existing_submission(db, user, request, key, request_hash, review_id, *, lock):
    if not user.is_active:
        raise HTTPException(401, "Session invalid or expired")
    if user.role == "student" and not request.enrollment_id:
        raise HTTPException(403, "Open this exercise through its learning path")
    if review_id:
        if user.role not in ("admin", "teacher"):
            raise HTTPException(404, "Class submission not found")
        original = db.get(Submission, review_id)
        version = db.get(ProblemVersion, original.problem_version_id) if original else None
        parent = db.get(Problem, version.problem_id) if version and version.problem_id else None
        if not parent:
            raise HTTPException(404, "Class submission not found")
        course_access(db, user, parent.course_id, edit=True, write=lock)
    if key:
        existing = db.scalar(select(Submission).where(Submission.idempotency_key == key, Submission.owner_id == user.id))
        if existing:
            if existing.request_hash != request_hash:
                raise HTTPException(409, "Idempotency key already used with different content")
            if user.role == "student":
                # A retry must not bypass a later privacy change, revocation or archive.
                authorize_step_submission(db, user, request, lock=lock)
            return serialize_submission(existing, db.scalar(select(Attempt).where(Attempt.submission_id == existing.id)))
    return None


def submission_context(request, mode, db, user, *, pinned, lock):
    problem = db.get(ProblemVersion, request.problem_version_id)
    if request.enrollment_id:
        authorize_step_submission(db, user, request, lock=lock)
    course = problem_access(db, user, problem, submit=True, pinned=pinned, lock=lock)
    if request.language not in problem.languages:
        raise HTTPException(422, "Language not allowed for this problem")
    if request.provider and user.role != "admin":
        raise HTTPException(403, "Provider override is reserved for administrators")
    name = choose_provider(request.provider, problem.provider, course.provider if course else None)
    try:
        revision = problem.provider_revision if name == problem.provider else None
        provider = provider_for(name, revision=revision, db=db)
        caps = provider.capabilities()
    except Exception:
        raise HTTPException(503, "Configured provider unavailable")
    if not caps["implemented"]:
        raise HTTPException(422, "Provider is reserved but not implemented yet")
    if request.language not in caps["languages"] or (mode == "run" and not caps["custom_input"]):
        raise HTTPException(422, "Provider does not support the requested operation")
    if problem.scoring_policy != "binary-v1" or problem.checker != "tokens-v1":
        raise HTTPException(422, "Unsupported scoring policy or checker")
    return problem, course, name, provider


def create_submission(request, mode, db, key, user, *, review_submission=None):
    key = str(UUID(key)) if key else None
    review_id = review_submission.id if review_submission else None
    request_hash = hashlib.sha256(json.dumps(
        {"mode": mode, **request.model_dump(mode="json"),
         **({"review_submission_id": review_id} if review_id else {})}, sort_keys=True, ensure_ascii=False,
    ).encode()).hexdigest()
    pinned = bool(request.enrollment_id) or review_id is not None
    existing = existing_submission(db, user, request, key, request_hash, review_id, lock=False)
    prepared = None
    if existing is None:
        problem, _, name, provider = submission_context(request, mode, db, user, pinned=pinned, lock=False)
        problem_id = problem.id
        prepared = (name, getattr(provider, "revision", None))
    # Release the read transaction/connection and stale ORM state before network I/O.
    db.rollback()
    if prepared is not None:
        if not provider.health_check():
            raise HTTPException(503, "Selected provider is not ready")
        provider.prepare_problem(problem_id)
    # Keep admission -> enrollment/course ordering; recheck mutable state after preflight.
    db.scalar(select(QuotaLock).where(QuotaLock.id == "admission").with_for_update())
    existing = existing_submission(db, user, request, key, request_hash, review_id, lock=True)
    if existing is not None:
        return existing
    problem, course, name, provider = submission_context(request, mode, db, user, pinned=pinned, lock=True)
    if prepared != (name, getattr(provider, "revision", None)):
        raise HTTPException(409, "Judging provider changed; retry the request")
    pending = db.scalar(select(func.count()).select_from(Attempt).where(
        Attempt.state.in_(["queued", "running", "retry_pending"])))
    if pending >= 50:
        raise HTTPException(429, "Local judging queue is full")
    own_pending = db.scalar(select(func.count()).select_from(Attempt).join(Submission).where(
        Submission.owner_id == user.id, Attempt.state.in_(["queued", "running", "retry_pending"])))
    hourly = db.scalar(select(func.count()).select_from(Submission).where(
        Submission.owner_id == user.id, Submission.created_at > utcnow() - timedelta(hours=1)))
    if own_pending >= 10 or hourly >= 40:
        raise HTTPException(429, "Account submission/run quota exceeded")
    if course:
        scope = select(Attempt).join(Submission, Attempt.submission_id == Submission.id).join(
            ProblemVersion, Submission.problem_version_id == ProblemVersion.id).join(
            Problem, ProblemVersion.problem_id == Problem.id).where(Problem.course_id == course.id)
        course_pending = db.scalar(select(func.count()).select_from(scope.where(
            Attempt.state.in_(["queued", "running", "retry_pending"])).subquery()))
        course_hourly = db.scalar(select(func.count()).select_from(scope.where(
            Submission.created_at > utcnow() - timedelta(hours=1)).subquery()))
        if course_pending >= 20 or course_hourly >= 200:
            raise HTTPException(429, "Class submission/run quota exceeded")
    submission = Submission(owner_id=user.id, problem_version_id=problem.id, language=request.language,
                            enrollment_id=str(request.enrollment_id) if request.enrollment_id else None,
                            path_step_id=str(request.path_step_id) if request.path_step_id else None,
                            source=request.source, mode=mode,
                            custom_input=request.input if mode == "run" else None,
                            idempotency_key=key, request_hash=request_hash)
    db.add(submission)
    try:
        db.flush()
        attempt = Attempt(submission_id=submission.id, provider=name, snapshot={
            "problem_version_id": problem.id, "language": request.language,
            "limits": problem.limits, "checker": problem.checker,
            "scoring_policy": problem.scoring_policy,
            "provider_revision": getattr(provider, "revision", None),
        })
        db.add(attempt)
        if review_id:
            audit(db, user, "submission.instructor_run", review_id, run_id=submission.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        # Concurrent retries with one key must return the original, not create a duplicate.
        existing = db.scalar(select(Submission).where(Submission.idempotency_key == key,
                                                     Submission.owner_id == user.id)) if key else None
        if existing and existing.request_hash == request_hash:
            return serialize_submission(existing, db.scalar(select(Attempt).where(Attempt.submission_id == existing.id)))
        raise HTTPException(409, "Submission conflict")
    # SQL is the persistent outbox; the scheduler dispatches queued attempts to Redis.
    return serialize_submission(submission, attempt)


def parse_key(value):
    try:
        return str(UUID(value)) if value else None
    except ValueError:
        raise HTTPException(422, "Idempotency-Key must be a UUID")


@app.post("/submissions", status_code=202)
def submit(request: SubmitRequest, user: User = Depends(current_user), db: Session = Depends(get_db),
           idempotency_key: str | None = Header(default=None)):
    return create_submission(request, "judge", db, parse_key(idempotency_key), user)


@app.post("/runs", status_code=202)
def run(request: RunRequest, user: User = Depends(current_user), db: Session = Depends(get_db),
        idempotency_key: str | None = Header(default=None)):
    return create_submission(request, "run", db, parse_key(idempotency_key), user)


@app.get("/submissions")
def list_submissions(offset: int = 0, course_id: str | None = None,
                     user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(Submission)
    if course_id:
        course_access(db, user, course_id, edit=True)
        query = query.join(ProblemVersion, Submission.problem_version_id == ProblemVersion.id).join(
            Problem, ProblemVersion.problem_id == Problem.id).where(Problem.course_id == course_id)
        audit(db, user, "submission.class_list_read", course_id)
        db.commit()
    else:
        query = own_submissions(user)
    rows = db.scalars(query.order_by(Submission.created_at.desc()).offset(max(0, offset)).limit(100))
    return [serialize_submission(s, db.scalar(select(Attempt).where(Attempt.submission_id == s.id))) for s in rows]


def own_submissions(user):
    query = select(Submission).where(Submission.owner_id == user.id)
    if user.role == "student":
        permitted = select(CourseMember.course_id).where(CourseMember.user_id == user.id,
                                                         CourseMember.access_source != "public")
        query = query.join(ProblemVersion, Submission.problem_version_id == ProblemVersion.id).outerjoin(
            Problem, ProblemVersion.problem_id == Problem.id).outerjoin(Course, Problem.course_id == Course.id).where(
            or_(Course.id.is_(None), and_(Course.archived.is_(False), or_(Course.is_public.is_(True), Course.id.in_(permitted)))))
    return query


@app.get("/my/stats")
def my_stats(user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = own_submissions(user).join(Attempt, Attempt.submission_id == Submission.id).where(
        Submission.mode == "judge", Attempt.state == "completed", Attempt.verdict == "ACCEPTED").with_only_columns(
        func.count(func.distinct(func.coalesce(Submission.path_step_id, Submission.problem_version_id))))
    return {"accepted_exercises": db.scalar(query)}


@app.post("/author/submissions/{submission_id}/run", status_code=202)
def replay_submission(submission_id: UUID, data: ReplayInput,
                      idempotency_key: str | None = Header(default=None),
                      user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role not in ("admin", "teacher"):
        raise HTTPException(404, "Submission not found")
    original = db.get(Submission, str(submission_id))
    if not original:
        raise HTTPException(404, "Submission not found")
    version = db.get(ProblemVersion, original.problem_version_id)
    problem = db.get(Problem, version.problem_id) if version.problem_id else None
    if not problem:
        raise HTTPException(404, "Class submission not found")
    # Replay the original source/language; never impersonate the learner or attach their enrollment.
    request = RunRequest(problem_version_id=version.id, language=original.language,
                         source=original.source, input=data.input)
    return create_submission(request, "run", db, parse_key(idempotency_key), user, review_submission=original)


@app.get("/submissions/{submission_id}")
def get_submission(submission_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    submission = db.get(Submission, str(submission_id))
    if not submission:
        raise HTTPException(404, "Submission not found")
    if user.role == "student":
        version = db.get(ProblemVersion, submission.problem_version_id)
        parent = db.get(Problem, version.problem_id) if version.problem_id else None
        if parent:
            course_access(db, user, parent.course_id)
    if submission.owner_id != user.id:
        permitted = user.role == "admin"
        version = db.get(ProblemVersion, submission.problem_version_id)
        problem = db.get(Problem, version.problem_id) if version.problem_id else None
        if problem:
            permitted = permitted or is_instructor(db, user, db.get(Course, problem.course_id))
        if not permitted:
            raise HTTPException(404, "Submission not found")
        audit(db, user, "submission.privileged_read", submission.id)
        db.commit()
    attempt = db.scalar(select(Attempt).where(Attempt.submission_id == submission.id))
    return serialize_submission(submission, attempt, include_source=True)
