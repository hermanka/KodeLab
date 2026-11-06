from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.mysql import MEDIUMTEXT


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class JudgePlugin(Base):
    __tablename__ = "judge_plugins"
    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    enabled: Mapped[bool] = mapped_column(default=False, server_default="0")
    active_revision: Mapped[str] = mapped_column(String(64))


class JudgePluginVersion(Base):
    __tablename__ = "judge_plugin_versions"
    __table_args__ = (UniqueConstraint("plugin_id", "version", name="uq_judge_plugin_version"),)
    revision: Mapped[str] = mapped_column(String(64), primary_key=True)
    plugin_id: Mapped[str] = mapped_column(ForeignKey("judge_plugins.id"), index=True)
    version: Mapped[str] = mapped_column(String(40))
    manifest: Mapped[dict] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(Text().with_variant(MEDIUMTEXT(), "mysql"))
    installed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(40), unique=True)
    full_name: Mapped[str] = mapped_column(String(120), default="", server_default="")
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default="student")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80), index=True)
    object_id: Mapped[str] = mapped_column(String(80))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RateBucket(Base):
    __tablename__ = "rate_buckets"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime)
    count: Mapped[int] = mapped_column(Integer, default=0)


class QuotaLock(Base):
    __tablename__ = "quota_locks"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (UniqueConstraint("invite_digest", name="uq_course_invite_digest"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    edit_revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    invite_digest: Mapped[str | None] = mapped_column(String(64))
    invite_ciphertext: Mapped[str | None] = mapped_column(Text)
    invite_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_public: Mapped[bool] = mapped_column(default=False)
    archived: Mapped[bool] = mapped_column(default=False, server_default="0")
    provider: Mapped[str | None] = mapped_column(String(30))


class CourseMember(Base):
    __tablename__ = "course_members"
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), default="student")
    access_source: Mapped[str] = mapped_column(String(20), default="assignment", server_default="assignment")


class Lesson(Base):
    __tablename__ = "lessons"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"))
    published_version_id: Mapped[str | None] = mapped_column(String(36))
    archived: Mapped[bool] = mapped_column(default=False)


class LessonVersion(Base):
    __tablename__ = "lesson_versions"
    __table_args__ = (UniqueConstraint("lesson_id", "revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    lesson_id: Mapped[str] = mapped_column(ForeignKey("lessons.id"))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    edit_revision: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(200))
    body_markdown: Mapped[str] = mapped_column(Text)
    body_html: Mapped[str] = mapped_column(Text().with_variant(MEDIUMTEXT(), "mysql"))
    status: Mapped[str] = mapped_column(String(20), default="draft")


class Problem(Base):
    __tablename__ = "problems"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"))
    published_version_id: Mapped[str | None] = mapped_column(String(80))
    archived: Mapped[bool] = mapped_column(default=False)


class ProblemVersion(Base):
    __tablename__ = "problem_versions"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    statement: Mapped[str] = mapped_column(Text)
    languages: Mapped[list] = mapped_column(JSON)
    limits: Mapped[dict] = mapped_column(JSON)
    provider: Mapped[str | None] = mapped_column(String(30))
    provider_revision: Mapped[str | None] = mapped_column(String(64))
    scoring_policy: Mapped[str] = mapped_column(String(30), default="binary-v1")
    checker: Mapped[str] = mapped_column(String(30), default="tokens-v1")
    problem_id: Mapped[str | None] = mapped_column(ForeignKey("problems.id"))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    edit_revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    __table_args__ = (UniqueConstraint("problem_id", "revision"),)
    validation_job_id: Mapped[str | None] = mapped_column(String(36))


class TestCase(Base):
    __tablename__ = "test_cases"
    __table_args__ = (UniqueConstraint("problem_version_id", "position"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    problem_version_id: Mapped[str] = mapped_column(ForeignKey("problem_versions.id"))
    position: Mapped[int] = mapped_column(Integer)
    input: Mapped[str] = mapped_column(Text)
    expected: Mapped[str] = mapped_column(Text)
    public: Mapped[bool]


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("owner_id", "idempotency_key", name="uq_submission_owner_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    problem_version_id: Mapped[str] = mapped_column(ForeignKey("problem_versions.id"))
    language: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(10))
    custom_input: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    enrollment_id: Mapped[str | None] = mapped_column(ForeignKey("path_enrollments.id"))
    path_step_id: Mapped[str | None] = mapped_column(ForeignKey("path_steps.id"))
    idempotency_key: Mapped[str | None] = mapped_column(String(36))
    request_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Attempt(Base):
    __tablename__ = "judging_attempts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), unique=True)
    provider: Mapped[str] = mapped_column(String(30))
    snapshot: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    verdict: Mapped[str | None] = mapped_column(String(40))
    score: Mapped[int | None]
    result: Mapped[dict | None] = mapped_column(JSON)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime)
    dispatch_after: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class ReferenceSolution(Base):
    __tablename__ = "reference_solutions"
    problem_version_id: Mapped[str] = mapped_column(ForeignKey("problem_versions.id"), primary_key=True)
    language: Mapped[str] = mapped_column(String(20), primary_key=True)
    source: Mapped[str] = mapped_column(Text)


class ValidationJob(Base):
    __tablename__ = "problem_validation_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    problem_version_id: Mapped[str] = mapped_column(ForeignKey("problem_versions.id"))
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    edit_revision: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(30))
    provider_revision: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    valid: Mapped[bool | None]
    result: Mapped[dict | None] = mapped_column(JSON)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime)
    dispatch_after: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class LearningPath(Base):
    __tablename__ = "learning_paths"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    published_version_id: Mapped[str | None] = mapped_column(String(36))
    archived: Mapped[bool] = mapped_column(default=False)


class PathVersion(Base):
    __tablename__ = "path_versions"
    __table_args__ = (UniqueConstraint("path_id", "revision", name="uq_path_revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    path_id: Mapped[str] = mapped_column(ForeignKey("learning_paths.id"))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    edit_revision: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    languages: Mapped[list] = mapped_column(JSON)
    sequential: Mapped[bool] = mapped_column(default=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")


class PathStep(Base):
    __tablename__ = "path_steps"
    __table_args__ = (UniqueConstraint("path_version_id", "key", name="uq_path_step_key"),
                      UniqueConstraint("path_version_id", "position", name="uq_path_step_position"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    path_version_id: Mapped[str] = mapped_column(ForeignKey("path_versions.id"), index=True)
    key: Mapped[str] = mapped_column(String(80))
    position: Mapped[int] = mapped_column(Integer)
    module: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20))
    required: Mapped[bool] = mapped_column(default=True)
    prerequisites: Mapped[list] = mapped_column(JSON)
    lesson_version_id: Mapped[str | None] = mapped_column(ForeignKey("lesson_versions.id"))
    problem_version_id: Mapped[str | None] = mapped_column(ForeignKey("problem_versions.id"))


class PathEnrollment(Base):
    __tablename__ = "path_enrollments"
    __table_args__ = (UniqueConstraint("user_id", "path_id", name="uq_user_path_enrollment"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    path_id: Mapped[str] = mapped_column(ForeignKey("learning_paths.id"))
    path_version_id: Mapped[str] = mapped_column(ForeignKey("path_versions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Completion(Base):
    __tablename__ = "step_completions"
    __table_args__ = (UniqueConstraint("enrollment_id", "step_id", name="uq_enrollment_completion"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    enrollment_id: Mapped[str] = mapped_column(ForeignKey("path_enrollments.id"), index=True)
    step_id: Mapped[str] = mapped_column(ForeignKey("path_steps.id"))
    attempt_id: Mapped[str | None] = mapped_column(ForeignKey("judging_attempts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
