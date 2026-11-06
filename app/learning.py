import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, field_validator, model_validator
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.auth import audit, current_user
from app.content import course_access, is_instructor, public_problem, RevisionInput
from app.contracts import Language, StrictModel
from app.db import get_db
from app.models import (Completion, Course, CourseMember, LearningPath, Lesson, LessonVersion, PathEnrollment,
                        PathStep, PathVersion, Problem, ProblemVersion, User, utcnow)

router = APIRouter(tags=["learning paths"])


class StepInput(StrictModel):
    key: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    module: str = Field(default="Dasar pemrograman", min_length=1, max_length=120)
    kind: Literal["reading", "exercise"]
    required: bool = True
    prerequisites: list[str] = Field(default_factory=list, max_length=60)
    lesson_version_id: str | None = None
    problem_version_id: str | None = None

    @field_validator("key")
    @classmethod
    def key_format(cls, value):
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", value):
            raise ValueError("Step key must contain lowercase letters, digits, underscore or hyphen")
        return value

    @model_validator(mode="after")
    def target(self):
        if self.kind == "reading" and (not self.lesson_version_id or self.problem_version_id):
            raise ValueError("Reading steps require only a material version")
        if self.kind == "exercise" and (not self.problem_version_id or self.lesson_version_id):
            raise ValueError("Exercise steps require only a problem version")
        return self


def dependency_graph(steps, sequential):
    keys = [s.key for s in steps]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate step key")
    graph, preceding = {}, []
    for step in steps:
        graph[step.key] = set(step.prerequisites) | (set(preceding) if sequential else set())
        if not graph[step.key].issubset(set(keys)):
            raise ValueError("Unknown prerequisite")
        if step.required:
            preceding.append(step.key)
    by_key = {s.key: s for s in steps}
    for step in steps:
        if step.required and any(not by_key[key].required for key in graph[step.key]):
            raise ValueError("Required steps cannot depend on optional steps")
    done, visiting = set(), set()

    def visit(key):
        if key in visiting:
            raise ValueError("Prerequisites contain a cycle")
        if key not in done:
            visiting.add(key)
            for parent in graph[key]:
                visit(parent)
            visiting.remove(key)
            done.add(key)

    for key in keys:
        visit(key)
    return graph


class PathInput(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=8000)
    languages: list[Language] = Field(default_factory=lambda: ["c17", "cpp17"], min_length=1, max_length=2)
    sequential: bool = True
    steps: list[StepInput] = Field(min_length=1, max_length=60)

    @model_validator(mode="after")
    def graph(self):
        dependency_graph(self.steps, self.sequential)
        if len(set(self.languages)) != len(self.languages):
            raise ValueError("Duplicate language")
        return self


class PathUpdate(PathInput):
    edit_revision: int = Field(ge=1)


def path_steps(db, version_id):
    return list(db.scalars(select(PathStep).where(PathStep.path_version_id == version_id).order_by(PathStep.position)))


def content_is_bound(db, kind, version_id):
    column = PathStep.lesson_version_id if kind == "reading" else PathStep.problem_version_id
    return db.scalar(select(PathStep.id).join(PathVersion).where(
        column == version_id, PathVersion.status == "published").limit(1)) is not None


def validate_targets(db, course_id, data):
    for step in data.steps:
        if step.kind == "reading":
            version = db.get(LessonVersion, step.lesson_version_id)
            parent = db.get(Lesson, version.lesson_id) if version else None
        else:
            version = db.get(ProblemVersion, step.problem_version_id)
            parent = db.get(Problem, version.problem_id) if version and version.problem_id else None
            if version and not set(data.languages).issubset(version.languages):
                raise HTTPException(422, "Every exercise must support the path's language profiles")
        if not version or not parent or parent.course_id != course_id or parent.archived or version.status != "published":
            raise HTTPException(422, "Steps must reference published, unarchived content in the same class")


def save_path_data(db, version, data, course_id):
    version.title, version.description = data.title, data.description
    version.languages, version.sequential = data.languages, data.sequential
    validate_targets(db, course_id, data)
    db.flush()
    db.execute(delete(PathStep).where(PathStep.path_version_id == version.id))
    for position, step in enumerate(data.steps, 1):
        db.add(PathStep(path_version_id=version.id, position=position, **step.model_dump()))


def private_path(db, version):
    path = db.get(LearningPath, version.path_id)
    return {"id": version.id, "path_id": version.path_id, "course_id": path.course_id,
            "revision": version.revision, "edit_revision": version.edit_revision,
            "title": version.title, "description": version.description, "languages": version.languages,
            "sequential": version.sequential, "status": version.status, "archived": path.archived,
            "steps": [{**{key: getattr(s, key) for key in StepInput.model_fields}, "id": s.id} for s in path_steps(db, version.id)]}


def editable_path(db, user, version_id, write=True):
    version = db.scalar(select(PathVersion).where(PathVersion.id == version_id).with_for_update())
    if not version:
        raise HTTPException(404, "Learning path not found")
    path = db.get(LearningPath, version.path_id)
    course_access(db, user, path.course_id, edit=True, write=write)
    return version, path


def completion_keys(db, enrollment, steps):
    ids = set(db.scalars(select(Completion.step_id).where(Completion.enrollment_id == enrollment.id)))
    return {s.key for s in steps if s.id in ids}


def enrollment_access(db, user, enrollment_id, lock=False):
    query = select(PathEnrollment).where(PathEnrollment.id == enrollment_id, PathEnrollment.user_id == user.id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    enrollment = db.scalar(query)
    if not enrollment:
        raise HTTPException(404, "Enrollment not found")
    path = db.get(LearningPath, enrollment.path_id)
    course_access(db, user, path.course_id, submit=True, write=lock)
    return enrollment


def step_access(db, enrollment, step_id):
    steps = path_steps(db, enrollment.path_version_id)
    step = next((s for s in steps if s.id == str(step_id)), None)
    if not step:
        raise HTTPException(404, "Learning step not found")
    version = db.get(PathVersion, enrollment.path_version_id)
    graph = dependency_graph(steps, version.sequential)
    done = completion_keys(db, enrollment, steps)
    if not graph[step.key].issubset(done):
        raise HTTPException(403, "Complete the prerequisites before opening this step")
    return step


def enrollment_summary(db, enrollment):
    return enrollment_summaries(db, [enrollment])[enrollment.id]


def enrollment_summaries(db, enrollments):
    if not enrollments:
        return {}
    versions = {v.id: v for v in db.scalars(select(PathVersion).where(
        PathVersion.id.in_({e.path_version_id for e in enrollments})))}
    paths = {p.id: p for p in db.scalars(select(LearningPath).where(
        LearningPath.id.in_({e.path_id for e in enrollments})))}
    courses = {c.id: c for c in db.scalars(select(Course).where(
        Course.id.in_({p.course_id for p in paths.values()})))}
    steps, completions = {}, {}
    for step in db.scalars(select(PathStep).where(PathStep.path_version_id.in_(versions)).order_by(PathStep.position)):
        steps.setdefault(step.path_version_id, []).append(step)
    for completion in db.scalars(select(Completion).where(Completion.enrollment_id.in_({e.id for e in enrollments}))):
        completions.setdefault(completion.enrollment_id, []).append(completion)
    return {e.id: summarize_enrollment(e, versions[e.path_version_id], paths[e.path_id],
                                      courses[paths[e.path_id].course_id], steps.get(e.path_version_id, []),
                                      completions.get(e.id, [])) for e in enrollments}


def summarize_enrollment(enrollment, version, path, course, steps, completions):
    completed_ids = {c.step_id for c in completions}
    done = {s.key for s in steps if s.id in completed_ids}
    graph = dependency_graph(steps, version.sequential)
    required = {s.key for s in steps if s.required}
    complete = bool(required) and required.issubset(done)
    rows = [{"id": s.id, "key": s.key, "title": s.title, "module": s.module, "kind": s.kind,
             "required": s.required, "completed": s.key in done,
             "locked": not graph[s.key].issubset(done), "prerequisites": sorted(graph[s.key])} for s in steps]
    next_step = next((s["id"] for s in rows if not s["locked"] and not s["completed"] and s["required"]), None)
    metrics = learning_metrics(enrollment, steps, completions)
    return {**metrics, "id": enrollment.id, "path_id": path.id, "path_version_id": version.id, "course_id": course.id,
            "course_title": course.title, "title": version.title, "description": version.description,
            "languages": version.languages, "revision": version.revision, "archived": path.archived, "course_archived": course.archived,
            "required_count": len(required), "completed_count": len(required & done), "complete": complete,
            "progress": round(len(required & done) / len(required) * 100) if required else None,
            "next_step_id": next_step, "steps": rows}


def learning_metrics(enrollment, steps, completions, now=None):
    """Server timestamps only; optional steps and repeat submissions cannot alter the finish time."""
    required = {s.id for s in steps if s.required}
    exercises = {s.id for s in steps if s.required and s.kind == "exercise"}
    done = {c.step_id: c.created_at for c in completions if c.step_id in required}
    finished = max(done.values()) if required and required.issubset(done) else None
    elapsed = max(0, ((finished or now or utcnow()) - enrollment.created_at).total_seconds())
    return {"started_at": enrollment.created_at.isoformat() + "Z",
            "completed_at": finished.isoformat() + "Z" if finished else None,
            "elapsed_seconds": round(elapsed, 3),
            "completion_seconds": round(elapsed, 3) if finished else None,
            "score": round(100 * len(exercises & done.keys()) / len(exercises), 2) if exercises else 0,
            "scored_exercises": len(exercises & done.keys()), "required_exercises": len(exercises)}


def leaderboard_rows(db, viewer, course_id=None):
    # Scope before aggregation: private classes must never leak through the global board.
    memberships = select(CourseMember.course_id).where(CourseMember.user_id == viewer.id, CourseMember.access_source != "public")
    query = (select(PathEnrollment, User, PathVersion).join(User, User.id == PathEnrollment.user_id)
             .join(PathVersion, PathVersion.id == PathEnrollment.path_version_id)
             .join(LearningPath, LearningPath.id == PathEnrollment.path_id)
             .join(Course, Course.id == LearningPath.course_id)
             .join(CourseMember, (CourseMember.course_id == Course.id) & (CourseMember.user_id == User.id))
             .where(User.role == "student", User.is_active.is_(True), PathVersion.status == "published"))
    if viewer.role != "admin":
        query = query.where(or_(Course.is_public.is_(True), Course.owner_id == viewer.id, Course.id.in_(memberships)))
    query = query.where(LearningPath.archived.is_(False))
    query = query.where(or_(Course.is_public.is_(True), CourseMember.access_source != "public"))
    if course_id:
        query = query.where(Course.id == course_id)
    else:
        query = query.where(Course.archived.is_(False))
    entries = list(db.execute(query))
    if not entries:
        return []
    steps, completions = {}, {}
    for step in db.scalars(select(PathStep).where(PathStep.path_version_id.in_({v.id for _, _, v in entries}))):
        steps.setdefault(step.path_version_id, []).append(step)
    for c in db.scalars(select(Completion).where(Completion.enrollment_id.in_({e.id for e, _, _ in entries}))):
        completions.setdefault(c.enrollment_id, []).append(c)
    now, rows = utcnow(), []
    for e, student, version in entries:
        metrics = learning_metrics(e, steps.get(version.id, []), completions.get(e.id, []), now)
        # Paths containing only reading material have progress but no coding score.
        if not metrics["required_exercises"]:
            continue
        rows.append({"user_id": student.id, "username": student.username, "full_name": student.full_name, "revision": version.revision,
                     "path_version_id": version.id, **metrics})
    return rows


def rank_leaderboard(rows):
    def key(row):
        return (-row["score"], row["completion_seconds"] if row["completion_seconds"] is not None else float("inf"))
    rows.sort(key=lambda row: (*key(row), row["username"].casefold(), row["user_id"]))
    previous, rank = None, 0
    for index, row in enumerate(rows, 1):
        if key(row) != previous:
            rank = index
        previous, row["rank"] = key(row), rank
    return rows


def aggregate_leaderboard(rows):
    students = {}
    for row in rows:
        student = students.setdefault(row["user_id"], {"user_id": row["user_id"], "username": row["username"], "full_name": row["full_name"],
            "score": 0, "completed_paths": 0, "scored_paths": 0, "completion_seconds": 0, "pending": False})
        student["score"] += row["score"]
        student["completed_paths"] += row["completed_at"] is not None
        if row["score"] > 0:
            student["scored_paths"] += 1
            student["pending"] |= row["completion_seconds"] is None
            student["completion_seconds"] += row["completion_seconds"] or 0
    for row in students.values():
        row["score"] = round(row["score"], 2)
        row["completion_seconds"] = None if row.pop("pending") or not row["scored_paths"] else round(row["completion_seconds"], 3)
    return rank_leaderboard(list(students.values()))


@router.get("/courses/{course_id}/leaderboard")
def class_leaderboard(course_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    course = course_access(db, user, course_id)
    return {"course_id": course.id, "title": course.title, "archived": course.archived,
            "rows": aggregate_leaderboard(leaderboard_rows(db, user, course_id=course.id))}


@router.get("/leaderboards")
def overall_leaderboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"rows": aggregate_leaderboard(leaderboard_rows(db, user))}


def authorize_step_submission(db, user, request, *, lock=True):
    enrollment = enrollment_access(db, user, str(request.enrollment_id), lock=lock)
    step = step_access(db, enrollment, request.path_step_id)
    if step.kind != "exercise" or step.problem_version_id != request.problem_version_id:
        raise HTTPException(422, "Submission does not match this learning step")
    if request.language not in db.get(PathVersion, enrollment.path_version_id).languages:
        raise HTTPException(422, "Language not allowed in this learning path")
    return enrollment, step


def record_accepted_completion(db, submission, attempt):
    if submission.mode != "judge" or attempt.verdict != "ACCEPTED" or attempt.score != 100 or not submission.enrollment_id:
        return
    enrollment = db.scalar(select(PathEnrollment).where(PathEnrollment.id == submission.enrollment_id).with_for_update())
    step = db.get(PathStep, submission.path_step_id)
    if not enrollment or not step or enrollment.user_id != submission.owner_id or step.path_version_id != enrollment.path_version_id:
        raise ValueError("Invalid persisted learning context")
    if step.problem_version_id != submission.problem_version_id or step.kind != "exercise":
        raise ValueError("Invalid persisted exercise context")
    if not db.scalar(select(Completion.id).where(Completion.enrollment_id == enrollment.id, Completion.step_id == step.id)):
        step_access(db, enrollment, step.id)
        db.add(Completion(enrollment_id=enrollment.id, step_id=step.id, attempt_id=attempt.id))
        audit(db, db.get(User, submission.owner_id), "learning.exercise_completed", step.id, enrollment_id=enrollment.id, attempt_id=attempt.id)


@router.post("/author/courses/{course_id}/paths", status_code=201)
def create_path(course_id: str, data: PathInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    course_access(db, user, course_id, edit=True, write=True)
    path = LearningPath(course_id=course_id)
    db.add(path)
    db.flush()
    version = PathVersion(path_id=path.id)
    db.add(version)
    save_path_data(db, version, data, course_id)
    audit(db, user, "path.draft_created", version.id)
    db.commit()
    return private_path(db, version)


@router.get("/author/path-versions/{version_id}")
def read_path(version_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    version, _ = editable_path(db, user, version_id, write=False)
    return private_path(db, version)


@router.put("/author/path-versions/{version_id}")
def update_path(version_id: str, data: PathUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    version, path = editable_path(db, user, version_id)
    if path.archived or version.status != "draft" or version.edit_revision != data.edit_revision:
        raise HTTPException(409, "Reload the editable draft before saving")
    save_path_data(db, version, data, path.course_id)
    version.edit_revision += 1
    audit(db, user, "path.draft_updated", version.id)
    db.commit()
    return private_path(db, version)


@router.post("/author/path-versions/{version_id}/publish")
def publish_path(version_id: str, data: RevisionInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    version, path = editable_path(db, user, version_id)
    if version.status != "draft" or version.edit_revision != data.edit_revision:
        raise HTTPException(409, "Only the current draft can be published")
    db.scalar(select(LearningPath).where(LearningPath.id == path.id).with_for_update().execution_options(populate_existing=True))
    previous = db.get(PathVersion, path.published_version_id) if path.published_version_id else None
    if path.archived or (previous and previous.revision >= version.revision):
        raise HTTPException(409, "Path archived or a newer revision already published")
    package = private_path(db, version)
    data = PathInput(**{**{key: package[key] for key in PathInput.model_fields if key != "steps"},
                         "steps": [{key: s[key] for key in StepInput.model_fields} for s in package["steps"]]})
    if not any(step.required for step in data.steps):
        raise HTTPException(422, "A published learning path requires at least one required step")
    validate_targets(db, path.course_id, data)
    version.status, path.published_version_id = "published", version.id
    audit(db, user, "path.published", version.id)
    db.commit()
    return private_path(db, version)


@router.post("/author/paths/{path_id}/versions", status_code=201)
def revise_path(path_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    path = db.scalar(select(LearningPath).where(LearningPath.id == path_id).with_for_update())
    if not path:
        raise HTTPException(404, "Path not found")
    course_access(db, user, path.course_id, edit=True, write=True)
    if path.archived:
        raise HTTPException(409, "Path archived")
    previous = db.scalar(select(PathVersion).where(PathVersion.path_id == path.id).order_by(PathVersion.revision.desc()).limit(1))
    package = private_path(db, previous)
    data = PathInput(**{**{key: package[key] for key in PathInput.model_fields if key != "steps"},
                         "steps": [{key: s[key] for key in StepInput.model_fields} for s in package["steps"]]})
    version = PathVersion(path_id=path.id, revision=previous.revision + 1)
    db.add(version)
    save_path_data(db, version, data, path.course_id)
    audit(db, user, "path.revision_created", version.id)
    db.commit()
    return private_path(db, version)


@router.post("/author/paths/{path_id}/archive")
def archive_path(path_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    path = db.scalar(select(LearningPath).where(LearningPath.id == path_id).with_for_update())
    if not path:
        raise HTTPException(404, "Path not found")
    course_access(db, user, path.course_id, edit=True, write=True)
    path.archived = True
    audit(db, user, "path.archived", path.id)
    db.commit()
    return {"status": "archived"}


@router.get("/author/courses/{course_id}/paths")
def author_paths(course_id: str, offset: int = 0, user: User = Depends(current_user), db: Session = Depends(get_db)):
    course_access(db, user, course_id, edit=True)
    return [private_path(db, v) for v in db.scalars(select(PathVersion).join(LearningPath).where(
        LearningPath.course_id == course_id).order_by(PathVersion.revision.desc(), PathVersion.id).offset(max(0, offset)).limit(100))]


@router.get("/author/courses/{course_id}/progress")
def class_progress(course_id: str, offset: int = Query(default=0, ge=0), user: User = Depends(current_user), db: Session = Depends(get_db)):
    from app.reports import class_rows
    course_access(db, user, course_id, edit=True)
    audit(db, user, "learning.class_progress_read", course_id)
    result = class_rows(db, course_id, offset)
    db.commit()
    return result


@router.get("/paths")
def catalog(course_id: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    member_courses = select(CourseMember.course_id).where(CourseMember.user_id == user.id, CourseMember.access_source != "public")
    query = select(PathVersion).join(LearningPath, LearningPath.published_version_id == PathVersion.id).join(Course)
    if course_id:
        course_access(db, user, course_id)
        query = query.where(LearningPath.course_id == course_id)
    if user.role != "admin":
        query = query.where(or_(Course.is_public.is_(True), Course.owner_id == user.id, Course.id.in_(member_courses)))
    rows = db.scalars(query.where(LearningPath.archived.is_(False), Course.archived.is_(False)).order_by(PathVersion.title).limit(100))
    result = []
    for version in rows:
        path = db.get(LearningPath, version.path_id)
        enrollment = db.scalar(select(PathEnrollment).where(PathEnrollment.user_id == user.id, PathEnrollment.path_id == path.id))
        steps = path_steps(db, version.id)
        result.append({"id": path.id, "title": version.title, "description": version.description,
            "course_id": path.course_id, "course_title": db.get(Course, path.course_id).title,
            "languages": version.languages, "revision": version.revision, "step_count": len(steps),
            "exercise_count": sum(s.kind == "exercise" for s in steps),
            "enrollment": enrollment_summary(db, enrollment) if enrollment else None})
    return result


@router.get("/courses/{course_id}/learning")
def course_learning(course_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    course = course_access(db, user, course_id)
    enrollments = db.scalars(select(PathEnrollment).join(LearningPath).where(
        LearningPath.course_id == course_id, PathEnrollment.user_id == user.id
    ).order_by(PathEnrollment.created_at.desc()))
    # Historical/archived paths and pinned revisions remain available to their
    # enrolled learners; another learner's enrollment is never exposed here.
    own = []
    for enrollment in enrollments:
        try:
            enrollment_access(db, user, enrollment.id)
        except HTTPException:
            continue
        own.append(enrollment_summary(db, enrollment))
    return {"course": {"id": course.id, "title": course.title, "description": course.description, "is_public": course.is_public,
                       "archived": course.archived, "can_manage": bool(is_instructor(db, user, course))},
            "paths": catalog(course_id=course_id, user=user, db=db), "enrollments": own}


@router.get("/my/learning")
def my_learning(user: User = Depends(current_user), db: Session = Depends(get_db)):
    result = []
    for enrollment in db.scalars(select(PathEnrollment).where(PathEnrollment.user_id == user.id).order_by(PathEnrollment.created_at.desc()).limit(100)):
        try:
            enrollment_access(db, user, enrollment.id)
        except HTTPException:
            continue
        result.append(enrollment_summary(db, enrollment))
    return result


@router.post("/paths/{path_id}/enroll")
def enroll_path(path_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    path = db.scalar(select(LearningPath).where(LearningPath.id == path_id).with_for_update())
    if not path:
        raise HTTPException(404, "Learning path not found")
    course = course_access(db, user, path.course_id)
    existing = db.scalar(select(PathEnrollment).where(PathEnrollment.user_id == user.id, PathEnrollment.path_id == path.id))
    if not existing:
        course = course_access(db, user, path.course_id, write=True)
        if course.archived or path.archived or not path.published_version_id:
            raise HTTPException(404, "Published path not found")
        version = db.get(PathVersion, path.published_version_id)
        # Revalidate content availability at enrollment; existing learners keep their pinned versions.
        package = private_path(db, version)
        data = PathInput(**{**{key: package[key] for key in PathInput.model_fields if key != "steps"},
                             "steps": [{key: s[key] for key in StepInput.model_fields} for s in package["steps"]]})
        validate_targets(db, course.id, data)
        if course.is_public:
            db.scalar(select(Course).where(Course.id == course.id).with_for_update())
            if not db.get(CourseMember, (course.id, user.id)):
                db.add(CourseMember(course_id=course.id, user_id=user.id, role="student", access_source="public"))
                db.flush()
        course_access(db, user, course.id, submit=True)
        existing = PathEnrollment(user_id=user.id, path_id=path.id, path_version_id=version.id)
        db.add(existing)
        db.flush()
        audit(db, user, "learning.enrolled", path.id, enrollment_id=existing.id, path_version_id=version.id)
        db.commit()
    else:
        course_access(db, user, course.id, submit=True)
    return enrollment_summary(db, existing)


@router.get("/enrollments/{enrollment_id}")
def read_enrollment(enrollment_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return enrollment_summary(db, enrollment_access(db, user, enrollment_id))


@router.get("/enrollments/{enrollment_id}/steps/{step_id}")
def read_step(enrollment_id: str, step_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    enrollment = enrollment_access(db, user, enrollment_id)
    step = step_access(db, enrollment, step_id)
    if step.kind == "reading":
        version = db.get(LessonVersion, step.lesson_version_id)
        content = {"id": version.id, "title": version.title, "body_html": version.body_html}
    else:
        content = public_problem(db, db.get(ProblemVersion, step.problem_version_id))
    return {"step_id": step.id, "kind": step.kind, "content": content, "enrollment": enrollment_summary(db, enrollment)}


@router.post("/enrollments/{enrollment_id}/steps/{step_id}/complete")
def complete_reading(enrollment_id: str, step_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    enrollment = enrollment_access(db, user, enrollment_id, lock=True)
    step = step_access(db, enrollment, step_id)
    if step.kind != "reading":
        raise HTTPException(409, "Exercise completion requires an accepted official submission")
    if not db.scalar(select(Completion.id).where(Completion.enrollment_id == enrollment.id, Completion.step_id == step.id)):
        db.add(Completion(enrollment_id=enrollment.id, step_id=step.id))
        audit(db, user, "learning.reading_confirmed", step.id, enrollment_id=enrollment.id)
        db.commit()
    return enrollment_summary(db, enrollment)
