"""Class lifecycle; academic data deletion is one transaction in FK-safe order."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.auth import audit, current_user
from app.contracts import StrictModel
from app.db import get_db
from app.models import (Attempt, Completion, Course, CourseMember, LearningPath, Lesson,
                        LessonVersion, PathEnrollment, PathStep, PathVersion, Problem,
                        ProblemVersion, QuotaLock, ReferenceSolution, Submission, TestCase,
                        User, ValidationJob)

router = APIRouter(tags=["class lifecycle"])


class DeleteClassInput(StrictModel):
    confirmation_title: str = Field(min_length=1, max_length=200)


def owned_course(db, user, course_id):
    # Match submission admission lock order; no new jobs can appear while deleting.
    db.scalar(select(QuotaLock).where(QuotaLock.id == "admission").with_for_update())
    course = db.scalar(select(Course).where(Course.id == course_id).with_for_update()
                       .execution_options(populate_existing=True))
    if not course or not (user.role == "admin" or (user.role == "teacher" and course.owner_id == user.id)):
        raise HTTPException(404, "Class not found or owner access required")
    return course


@router.post("/courses/{course_id}/archive")
def archive_course(course_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    course = owned_course(db, user, course_id)
    if not course.archived:
        course.archived = True
        audit(db, user, "course.archived", course.id)
    db.commit()
    return {"id": course.id, "archived": True}


@router.post("/courses/{course_id}/restore")
def restore_course(course_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    course = owned_course(db, user, course_id)
    if course.archived:
        course.archived = False
        audit(db, user, "course.restored", course.id)
    db.commit()
    return {"id": course.id, "archived": False}


@router.delete("/courses/{course_id}")
def delete_course(course_id: str, data: DeleteClassInput,
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    course = owned_course(db, user, course_id)
    if data.confirmation_title != course.title:
        raise HTTPException(422, "Class name confirmation does not match")
    # Snapshot IDs before any deletion. Avoid MySQL target-table/subquery limitations.
    def ids(model, condition):
        return list(db.scalars(select(model.id).where(condition)))

    problems = ids(Problem, Problem.course_id == course_id)
    versions = ids(ProblemVersion, ProblemVersion.problem_id.in_(problems))
    lessons = ids(Lesson, Lesson.course_id == course_id)
    paths = ids(LearningPath, LearningPath.course_id == course_id)
    path_versions = ids(PathVersion, PathVersion.path_id.in_(paths))
    steps = ids(PathStep, PathStep.path_version_id.in_(path_versions))
    enrollments = ids(PathEnrollment, PathEnrollment.path_id.in_(paths))
    submissions = ids(Submission, or_(Submission.problem_version_id.in_(versions),
                      Submission.enrollment_id.in_(enrollments), Submission.path_step_id.in_(steps)))
    attempts = list(db.scalars(select(Attempt).where(Attempt.submission_id.in_(submissions))
                              .order_by(Attempt.id).with_for_update()))
    validations = list(db.scalars(select(ValidationJob).where(ValidationJob.problem_version_id.in_(versions))
                                 .order_by(ValidationJob.id).with_for_update()))
    # Queued/retry messages will become harmless no-ops after commit. Running jobs
    # finish normally; asking the caller to retry avoids racing their final writes.
    if any(job.state == "running" for job in [*attempts, *validations]):
        raise HTTPException(409, "Class has running judging jobs; wait for them to finish before deletion")
    operations = [
        (Completion, or_(Completion.enrollment_id.in_(enrollments), Completion.step_id.in_(steps),
                         Completion.attempt_id.in_([a.id for a in attempts]))),
        (Attempt, Attempt.submission_id.in_(submissions)),
        (Submission, Submission.id.in_(submissions)),
        (PathEnrollment, PathEnrollment.id.in_(enrollments)),
        (PathStep, PathStep.id.in_(steps)),
        (PathVersion, PathVersion.id.in_(path_versions)),
        (LearningPath, LearningPath.id.in_(paths)),
        (ValidationJob, ValidationJob.problem_version_id.in_(versions)),
        (ReferenceSolution, ReferenceSolution.problem_version_id.in_(versions)),
        (TestCase, TestCase.problem_version_id.in_(versions)),
        (ProblemVersion, ProblemVersion.id.in_(versions)),
        (Problem, Problem.id.in_(problems)),
        (LessonVersion, LessonVersion.lesson_id.in_(lessons)),
        (Lesson, Lesson.id.in_(lessons)),
        (CourseMember, CourseMember.course_id == course_id),
        (Course, Course.id == course_id),
    ]
    for model, condition in operations:
        db.execute(delete(model).where(condition).execution_options(synchronize_session=False))
    audit(db, user, "course.deleted", course_id)
    db.commit()
    return {"status": "deleted", "id": course_id}
