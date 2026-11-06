from datetime import timedelta
from typing import Literal

import bleach
from fastapi import APIRouter, Depends, HTTPException
from markdown_it import MarkdownIt
from pydantic import Field, field_validator, model_validator
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.auth import audit, current_user
from app.contracts import Language, Limits, StrictModel, SubmitRequest
from app.db import get_db
from app.models import (Course, CourseMember, JudgePluginVersion, Lesson, LessonVersion, Problem, ProblemVersion,
                        QuotaLock, ReferenceSolution, TestCase, User, ValidationJob, new_id, utcnow)
from app.providers import choose_provider, provider_for

router = APIRouter(tags=["courses and authoring"])


def render_markdown(value):
    html = MarkdownIt("commonmark", {"html": False}).disable("image").render(value)
    return bleach.clean(html, tags={"p", "br", "strong", "em", "s", "blockquote", "ul", "ol", "li",
                                    "pre", "code", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "a"},
                        attributes={"a": ["href", "title"]}, protocols={"http", "https", "mailto"}, strip=True)


def is_instructor(db, user, course):
    if user.role == "admin":
        return True
    member = db.get(CourseMember, (course.id, user.id))
    return user.role == "teacher" and (course.owner_id == user.id or (member and member.role == "teacher"))


def course_access(db, user, course_id, *, edit=False, submit=False, write=False):
    course = db.scalar(select(Course).where(Course.id == course_id).with_for_update().execution_options(populate_existing=True)) if write else db.get(Course, course_id)
    if not course:
        raise HTTPException(404, "Course not found")
    if course.archived and user.role == "student":
        raise HTTPException(404, "Course not found")
    if course.archived and not is_instructor(db, user, course) and not db.get(CourseMember, (course.id, user.id)):
        raise HTTPException(404, "Course not found")
    if is_instructor(db, user, course):
        if write and course.archived:
            raise HTTPException(409, "Class archived; restore it before making changes")
        return course
    member = db.get(CourseMember, (course.id, user.id))
    if edit or (submit and not member) or (not course.is_public and (not member or member.access_source == "public")):
        raise HTTPException(404, "Course not found")
    if write and course.archived:
        raise HTTPException(409, "Class archived; restore it before making changes")
    return course


def problem_access(db, user, version, *, submit=False, pinned=False, lock=True):
    if not version or version.status != "published":
        raise HTTPException(404, "Published problem not found")
    if user.role == "student" and not pinned:
        raise HTTPException(403, "Open this exercise through its learning path")
    if not version.problem_id:
        return None  # Published legacy sample, available to authenticated users.
    problem = db.get(Problem, version.problem_id)
    course = course_access(db, user, problem.course_id, submit=submit, write=submit and lock)
    if submit and course.archived:
        raise HTTPException(409, "Class archived; restore it before making changes")
    if not pinned and (problem.archived or (submit and problem.published_version_id != version.id)):
        raise HTTPException(404, "Published problem not found")
    if not pinned and not is_instructor(db, user, course):
        from app.learning import content_is_bound
        if content_is_bound(db, "exercise", version.id):
            raise HTTPException(403, "Open this exercise through its learning path")
    return course


def public_problem(db, version):
    return {"id": version.id, "problem_id": version.problem_id, "title": version.title,
            "statement": version.statement, "statement_html": render_markdown(version.statement),
            "languages": version.languages, "limits": version.limits, "revision": version.revision,
            "scoring_policy": version.scoring_policy,
            "samples": [{"input": t.input, "expected": t.expected} for t in db.scalars(select(TestCase).where(
                TestCase.problem_version_id == version.id, TestCase.public.is_(True)).order_by(TestCase.position))]}


class CourseInput(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=8000)
    is_public: bool = False

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value):
        if not value.strip():
            raise ValueError("Class name cannot be blank")
        return value.strip()


class MemberInput(StrictModel):
    user_id: str | None = Field(default=None, max_length=36)
    username: str | None = Field(default=None, min_length=3, max_length=40)
    role: Literal["student", "teacher"] = "student"

    @model_validator(mode="after")
    def identity(self):
        if bool(self.user_id) == bool(self.username):
            raise ValueError("Supply a user ID or username")
        return self


class RevisionInput(StrictModel):
    edit_revision: int = Field(ge=1)


class LessonInput(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    body_markdown: str = Field(min_length=1, max_length=32768)

    @field_validator("body_markdown")
    @classmethod
    def byte_limit(cls, value):
        if len(value.encode()) > 32768:
            raise ValueError("Material must be <=32768 UTF-8 bytes")
        return value


class LessonUpdate(LessonInput):
    edit_revision: int = Field(ge=1)


class CaseInput(StrictModel):
    input: str = Field(max_length=32768)
    expected: str = Field(max_length=32768)
    public: bool = False

    @field_validator("input", "expected")
    @classmethod
    def byte_limit(cls, value):
        if len(value.encode()) > 32768 or "\x00" in value:
            raise ValueError("Test data must be <=32768 UTF-8 bytes and contain no NUL")
        return value


class ProblemInput(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    statement: str = Field(min_length=1, max_length=16384)
    languages: list[Language] = Field(min_length=1, max_length=2)
    limits: Limits = Field(default_factory=Limits)
    provider: str = Field(default="custom", pattern=r"^[a-z][a-z0-9-]{0,29}$")
    cases: list[CaseInput] = Field(min_length=1, max_length=10)
    reference_solutions: dict[Language, str]

    @model_validator(mode="after")
    def validate_package(self):
        if len(set(self.languages)) != len(self.languages):
            raise ValueError("Duplicate language profile")
        if set(self.languages) != set(self.reference_solutions):
            raise ValueError("Exactly one reference solution is required for each allowed language")
        for language, source in self.reference_solutions.items():
            SubmitRequest(language=language, source=source)
        if not any(case.public for case in self.cases):
            raise ValueError("At least one public sample is required")
        return self


class ProblemUpdate(ProblemInput):
    edit_revision: int = Field(ge=1)


def private_lesson(db, version):
    lesson = db.get(Lesson, version.lesson_id)
    return {"id": version.id, "lesson_id": lesson.id, "course_id": lesson.course_id,
            "archived": lesson.archived,
            "revision": version.revision, "edit_revision": version.edit_revision,
            "status": version.status, "title": version.title,
            "body_markdown": version.body_markdown, "body_html": version.body_html}


def get_lesson_draft(db, user, version_id, allow_archived=False, write=True):
    version = db.scalar(select(LessonVersion).where(LessonVersion.id == version_id).with_for_update())
    if not version:
        raise HTTPException(404, "Material not found")
    lesson = db.get(Lesson, version.lesson_id)
    course_access(db, user, lesson.course_id, edit=True, write=write)
    if lesson.archived and not allow_archived:
        raise HTTPException(409, "Material is archived")
    return version, lesson


def get_problem_draft(db, user, version_id, allow_archived=False, write=True):
    version = db.scalar(select(ProblemVersion).where(ProblemVersion.id == version_id).with_for_update())
    if not version or not version.problem_id:
        raise HTTPException(404, "Problem not found")
    problem = db.get(Problem, version.problem_id)
    course_access(db, user, problem.course_id, edit=True, write=write)
    if problem.archived and not allow_archived:
        raise HTTPException(409, "Problem is archived")
    return version, problem


def assert_editable(version, revision):
    if version.status != "draft":
        raise HTTPException(409, "Only drafts can be edited or published")
    if version.edit_revision != revision:
        raise HTTPException(409, "Draft changed; reload before continuing")


def private_problem(db, version):
    plugin_version = db.get(JudgePluginVersion, version.provider_revision) if version.provider_revision else None
    return {"id": version.id, "problem_id": version.problem_id, "revision": version.revision,
            "archived": db.get(Problem, version.problem_id).archived,
            "edit_revision": version.edit_revision, "status": version.status,
            "title": version.title, "statement": version.statement, "languages": version.languages,
            "limits": version.limits, "provider": version.provider, "provider_revision": version.provider_revision,
            "provider_version": plugin_version.version if plugin_version else None,
            "validation_job_id": version.validation_job_id,
            "cases": [{"input": t.input, "expected": t.expected, "public": t.public} for t in db.scalars(
                select(TestCase).where(TestCase.problem_version_id == version.id).order_by(TestCase.position))],
            "reference_solutions": {r.language: r.source for r in db.scalars(select(ReferenceSolution).where(
                ReferenceSolution.problem_version_id == version.id))}}


def set_problem_data(db, version, data):
    if data.provider not in ("custom", "domjudge"):
        from app.providers import ProviderUnavailable
        try:
            with db.no_autoflush:
                provider_for(data.provider, db=db)
        except ProviderUnavailable:
            raise HTTPException(422, "Select an active judging plugin")
    version.title, version.statement = data.title, data.statement
    version.languages, version.limits, version.provider = data.languages, data.limits.model_dump(), data.provider
    version.scoring_policy, version.checker = "binary-v1", "tokens-v1"
    version.validation_job_id = None
    version.provider_revision = None
    db.flush()
    db.execute(delete(TestCase).where(TestCase.problem_version_id == version.id))
    db.execute(delete(ReferenceSolution).where(ReferenceSolution.problem_version_id == version.id))
    for position, case in enumerate(data.cases, 1):
        db.add(TestCase(problem_version_id=version.id, position=position, **case.model_dump()))
    for language, source in data.reference_solutions.items():
        db.add(ReferenceSolution(problem_version_id=version.id, language=language, source=source))


@router.post("/courses", status_code=201)
def create_course(data: CourseInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role not in ("teacher", "admin"):
        raise HTTPException(403, "Teacher access required")
    course = Course(owner_id=user.id, **data.model_dump())
    db.add(course)
    db.flush()
    audit(db, user, "course.created", course.id)
    db.commit()
    return {"id": course.id, "title": course.title, "description": course.description, "is_public": course.is_public, "archived": course.archived, "owner_id": course.owner_id}


@router.get("/courses")
def list_courses(offset: int = 0, status: Literal["active", "archived"] | None = None,
                 managed: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(Course)
    if status:
        query = query.where(Course.archived.is_(status == "archived"))
    if user.role == "student":
        query = query.where(Course.archived.is_(False))
    if user.role != "admin":
        memberships = select(CourseMember.course_id).where(CourseMember.user_id == user.id, CourseMember.access_source != "public")
        query = query.where(or_((Course.is_public.is_(True) & Course.archived.is_(False)), Course.owner_id == user.id, Course.id.in_(memberships)))
    if managed and user.role != "admin":
        if user.role != "teacher":
            return []
        assigned = select(CourseMember.course_id).where(CourseMember.user_id == user.id, CourseMember.role == "teacher")
        query = query.where(or_(Course.owner_id == user.id, Course.id.in_(assigned)))
    return [course_view(db, user, c) for c in db.scalars(query.order_by(Course.id).offset(max(0, offset)).limit(100))]


def course_view(db, user, course):
    return {"id": course.id, "title": course.title, "description": course.description,
            "is_public": course.is_public, "owner_id": course.owner_id, "archived": course.archived,
            "can_manage": bool(is_instructor(db, user, course)),
            "can_delete": user.role == "admin" or (user.role == "teacher" and course.owner_id == user.id)}


@router.get("/courses/{course_id}")
def read_course(course_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return course_view(db, user, course_access(db, user, course_id))


@router.post("/courses/{course_id}/members", status_code=201)
def add_member(course_id: str, data: MemberInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    course = course_access(db, user, course_id, edit=True, write=True)
    if user.role != "admin" and course.owner_id != user.id:
        raise HTTPException(403, "Only the owner can change class assignments")
    target = db.get(User, data.user_id) if data.user_id else db.scalar(select(User).where(User.username == data.username.strip().lower()))
    if not target or not target.is_active or (data.role == "teacher" and target.role != "teacher"):
        raise HTTPException(422, "Account does not support the requested class role")
    db.scalar(select(Course).where(Course.id == course_id).with_for_update())
    membership = db.get(CourseMember, (course_id, target.id))
    if membership:
        membership.role = data.role
        membership.access_source = "assignment"
    else:
        db.add(CourseMember(course_id=course_id, user_id=target.id, role=data.role))
    audit(db, user, "course.member_assigned", course_id, user_id=target.id, role=data.role, access_source="assignment")
    db.commit()
    return {"user_id": target.id, "role": data.role}


@router.delete("/courses/{course_id}/members/{member_id}")
def remove_member(course_id: str, member_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    course = course_access(db, user, course_id, edit=True, write=True)
    if user.role != "admin" and course.owner_id != user.id:
        raise HTTPException(403, "Only the owner can change class assignments")
    db.execute(delete(CourseMember).where(CourseMember.course_id == course_id, CourseMember.user_id == member_id))
    audit(db, user, "course.member_removed", course_id, user_id=member_id)
    db.commit()
    return {"status": "removed"}


@router.get("/courses/{course_id}/members")
def list_members(course_id: str, offset: int = 0, user: User = Depends(current_user), db: Session = Depends(get_db)):
    course_access(db, user, course_id, edit=True)
    rows = db.execute(select(User.id, User.username, CourseMember.role).join(
        CourseMember, CourseMember.user_id == User.id).where(CourseMember.course_id == course_id).order_by(
            User.username).offset(max(0, offset)).limit(100)).mappings()
    return [dict(row) for row in rows]


@router.post("/courses/{course_id}/enroll")
def enroll(course_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    course = course_access(db, user, course_id, write=True)
    db.scalar(select(Course).where(Course.id == course_id).with_for_update())
    if not course.is_public:
        raise HTTPException(403, "Private class enrollment requires assignment")
    if not db.get(CourseMember, (course.id, user.id)):
        db.add(CourseMember(course_id=course.id, user_id=user.id, role="student", access_source="public"))
    audit(db, user, "course.enrolled", course.id)
    db.commit()
    return {"course_id": course.id, "status": "enrolled"}


@router.post("/author/courses/{course_id}/lessons", status_code=201)
def create_lesson(course_id: str, data: LessonInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    course_access(db, user, course_id, edit=True, write=True)
    lesson = Lesson(course_id=course_id)
    db.add(lesson)
    db.flush()
    version = LessonVersion(lesson_id=lesson.id, **data.model_dump(), body_html=render_markdown(data.body_markdown))
    db.add(version)
    db.flush()
    audit(db, user, "material.draft_created", version.id)
    db.commit()
    return private_lesson(db, version)


@router.get("/author/lesson-versions/{version_id}")
def read_lesson_draft(version_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    version, _ = get_lesson_draft(db, user, version_id, allow_archived=True, write=False)
    return private_lesson(db, version)


@router.put("/author/lesson-versions/{version_id}")
def update_lesson(version_id: str, data: LessonUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    version, _ = get_lesson_draft(db, user, version_id)
    assert_editable(version, data.edit_revision)
    version.title, version.body_markdown = data.title, data.body_markdown
    version.body_html = render_markdown(data.body_markdown)
    version.edit_revision += 1
    audit(db, user, "material.draft_updated", version.id, edit_revision=version.edit_revision)
    db.commit()
    return private_lesson(db, version)


@router.post("/author/lesson-versions/{version_id}/publish")
def publish_lesson(version_id: str, data: RevisionInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    version, lesson = get_lesson_draft(db, user, version_id)
    assert_editable(version, data.edit_revision)
    db.scalar(select(Lesson).where(Lesson.id == lesson.id).with_for_update().execution_options(populate_existing=True))
    if lesson.archived:
        raise HTTPException(409, "Material is archived")
    previous = db.get(LessonVersion, lesson.published_version_id) if lesson.published_version_id else None
    if previous and previous.revision >= version.revision:
        raise HTTPException(409, "A newer version is already published")
    version.status, lesson.published_version_id = "published", version.id
    audit(db, user, "material.published", version.id)
    db.commit()
    return private_lesson(db, version)


@router.post("/author/lessons/{lesson_id}/versions", status_code=201)
def revise_lesson(lesson_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    lesson = db.scalar(select(Lesson).where(Lesson.id == lesson_id).with_for_update())
    if not lesson:
        raise HTTPException(404, "Material not found")
    course_access(db, user, lesson.course_id, edit=True, write=True)
    if lesson.archived:
        raise HTTPException(409, "Material is archived")
    previous = db.scalar(select(LessonVersion).where(LessonVersion.lesson_id == lesson_id).order_by(LessonVersion.revision.desc()).limit(1))
    version = LessonVersion(lesson_id=lesson_id, revision=previous.revision + 1, title=previous.title,
                            body_markdown=previous.body_markdown, body_html=previous.body_html)
    db.add(version)
    db.flush()
    audit(db, user, "material.revision_created", version.id)
    db.commit()
    return private_lesson(db, version)


@router.get("/courses/{course_id}/lessons")
def published_lessons(course_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    course = course_access(db, user, course_id)
    rows = db.scalars(select(LessonVersion).join(Lesson, Lesson.published_version_id == LessonVersion.id).where(
        Lesson.course_id == course_id, Lesson.archived.is_(False), LessonVersion.status == "published").limit(100))
    from app.learning import content_is_bound
    return [{"id": v.id, "lesson_id": v.lesson_id, "revision": v.revision, "title": v.title, "body_html": v.body_html}
            for v in rows if is_instructor(db, user, course) or not content_is_bound(db, "reading", v.id)]


@router.post("/author/courses/{course_id}/problems", status_code=201)
def create_problem(course_id: str, data: ProblemInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    course_access(db, user, course_id, edit=True, write=True)
    problem = Problem(course_id=course_id)
    db.add(problem)
    db.flush()
    version = ProblemVersion(id=new_id(), problem_id=problem.id)
    db.add(version)
    set_problem_data(db, version, data)
    audit(db, user, "problem.draft_created", version.id)
    db.commit()
    return private_problem(db, version)


@router.get("/author/problem-versions/{version_id}")
def read_problem_draft(version_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    version, _ = get_problem_draft(db, user, version_id, allow_archived=True, write=False)
    audit(db, user, "problem.keys_read", version.id)
    result = private_problem(db, version)
    db.commit()
    return result


@router.put("/author/problem-versions/{version_id}")
def update_problem(version_id: str, data: ProblemUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    version, _ = get_problem_draft(db, user, version_id)
    assert_editable(version, data.edit_revision)
    set_problem_data(db, version, data)
    version.edit_revision += 1
    audit(db, user, "problem.draft_updated", version.id, edit_revision=version.edit_revision)
    db.commit()
    return private_problem(db, version)


@router.post("/author/problems/{problem_id}/versions", status_code=201)
def revise_problem(problem_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    problem = db.scalar(select(Problem).where(Problem.id == problem_id).with_for_update())
    if not problem:
        raise HTTPException(404, "Problem not found")
    course_access(db, user, problem.course_id, edit=True, write=True)
    if problem.archived:
        raise HTTPException(409, "Problem is archived")
    previous = db.scalar(select(ProblemVersion).where(ProblemVersion.problem_id == problem_id).order_by(ProblemVersion.revision.desc()).limit(1))
    package = private_problem(db, previous)
    version = ProblemVersion(id=new_id(), problem_id=problem_id, revision=previous.revision + 1)
    db.add(version)
    set_problem_data(db, version, ProblemInput(**{k: package[k] for k in ProblemInput.model_fields}))
    audit(db, user, "problem.revision_created", version.id)
    db.commit()
    return private_problem(db, version)


@router.post("/author/problem-versions/{version_id}/validate", status_code=202)
def validate_problem(version_id: str, data: RevisionInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.scalar(select(QuotaLock).where(QuotaLock.id == "admission").with_for_update())
    version, problem = get_problem_draft(db, user, version_id)
    assert_editable(version, data.edit_revision)
    provider = provider_for(choose_provider(None, version.provider), db=db)
    caps = provider.capabilities()
    if not caps["implemented"] or not set(version.languages).issubset(caps["languages"]):
        raise HTTPException(422, "Provider does not support this package")
    if not provider.health_check():
        raise HTTPException(503, "Provider not ready")
    pending = db.scalar(select(func.count()).select_from(ValidationJob).where(
        ValidationJob.actor_id == user.id, ValidationJob.state.in_(["queued", "running", "retry_pending"])))
    hourly = db.scalar(select(func.count()).select_from(ValidationJob).where(
        ValidationJob.actor_id == user.id, ValidationJob.created_at > utcnow() - timedelta(hours=1)))
    total = db.scalar(select(func.count()).select_from(ValidationJob).where(ValidationJob.state.in_(["queued", "running", "retry_pending"])))
    class_jobs = select(ValidationJob).join(ProblemVersion, ValidationJob.problem_version_id == ProblemVersion.id).join(
        Problem, ProblemVersion.problem_id == Problem.id).where(Problem.course_id == problem.course_id)
    class_pending = db.scalar(select(func.count()).select_from(class_jobs.where(
        ValidationJob.state.in_(["queued", "running", "retry_pending"])).subquery()))
    class_hourly = db.scalar(select(func.count()).select_from(class_jobs.where(
        ValidationJob.created_at > utcnow() - timedelta(hours=1)).subquery()))
    if pending >= 2 or hourly >= 10 or total >= 10 or class_pending >= 4 or class_hourly >= 20:
        raise HTTPException(429, "Reference validation quota exceeded")
    job = ValidationJob(id=new_id(), problem_version_id=version.id, actor_id=user.id,
                        edit_revision=version.edit_revision, provider=version.provider,
                        provider_revision=getattr(provider, "revision", None))
    version.provider_revision = job.provider_revision
    version.status, version.validation_job_id = "validating", job.id
    db.add(job)
    audit(db, user, "problem.validation_requested", version.id, validation_job_id=job.id)
    db.commit()
    return {"id": job.id, "state": job.state, "problem_version_id": version.id}


@router.get("/author/validations/{job_id}")
def read_validation(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = db.get(ValidationJob, job_id)
    if not job:
        raise HTTPException(404, "Validation not found")
    get_problem_draft(db, user, job.problem_version_id, allow_archived=True, write=False)
    audit(db, user, "problem.validation_result_read", job.id)
    result = {"id": job.id, "state": job.state, "valid": job.valid, "result": job.result,
              "error_code": job.error_code, "edit_revision": job.edit_revision}
    db.commit()
    return result


@router.post("/author/problem-versions/{version_id}/publish")
def publish_problem(version_id: str, data: RevisionInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.scalar(select(QuotaLock).where(QuotaLock.id == "admission").with_for_update())
    version, problem = get_problem_draft(db, user, version_id)
    assert_editable(version, data.edit_revision)
    job = db.get(ValidationJob, version.validation_job_id) if version.validation_job_id else None
    if (not job or job.state != "completed" or not job.valid or job.edit_revision != version.edit_revision
            or job.provider != version.provider or job.provider_revision != version.provider_revision):
        raise HTTPException(409, "Current draft must pass reference validation before publication")
    db.scalar(select(Problem).where(Problem.id == problem.id).with_for_update().execution_options(populate_existing=True))
    if problem.archived:
        raise HTTPException(409, "Problem is archived")
    previous = db.get(ProblemVersion, problem.published_version_id) if problem.published_version_id else None
    if previous and previous.revision >= version.revision:
        raise HTTPException(409, "A newer version is already published")
    provider = provider_for(version.provider, revision=version.provider_revision, db=db)
    if not provider.health_check():
        raise HTTPException(503, "Provider not ready")
    provider.prepare_problem(version.id)
    version.status, problem.published_version_id = "published", version.id
    audit(db, user, "problem.published", version.id, validation_job_id=job.id)
    db.commit()
    return private_problem(db, version)


@router.get("/author/courses/{course_id}/content")
def author_catalog(course_id: str, offset: int = 0, user: User = Depends(current_user), db: Session = Depends(get_db)):
    course_access(db, user, course_id, edit=True)
    lessons = db.execute(select(LessonVersion.id, LessonVersion.lesson_id, LessonVersion.title, LessonVersion.status,
        LessonVersion.revision, Lesson.archived).join(Lesson).where(Lesson.course_id == course_id)
        .order_by(LessonVersion.id).offset(max(0, offset)).limit(100)).mappings().all()
    problems = db.execute(select(ProblemVersion.id, ProblemVersion.problem_id, ProblemVersion.title, ProblemVersion.status,
        ProblemVersion.revision, Problem.archived).join(Problem).where(Problem.course_id == course_id)
        .order_by(ProblemVersion.id).offset(max(0, offset)).limit(100)).mappings().all()
    return {"lessons": [dict(row) for row in lessons], "problems": [dict(row) for row in problems]}


@router.post("/author/{kind}/{item_id}/archive")
def archive_item(kind: Literal["lessons", "problems"], item_id: str,
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    model = Lesson if kind == "lessons" else Problem
    item = db.scalar(select(model).where(model.id == item_id).with_for_update())
    if not item:
        raise HTTPException(404, "Content not found")
    course_access(db, user, item.course_id, edit=True, write=True)
    item.archived = True
    audit(db, user, "content.archived", item.id, kind=kind)
    db.commit()
    return {"status": "archived"}
