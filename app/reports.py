"""Instructor reports: class totals, per-path participants and pinned work history."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth import audit, current_user
from app.content import course_access
from app.db import get_db
from app.learning import enrollment_summary, enrollment_summaries
from app.models import (Attempt, CourseMember, LearningPath, PathEnrollment, PathStep,
                        PathVersion, Submission, User)

router = APIRouter(tags=["instructor progress"])


def participants(db, course_id):
    members = select(CourseMember.user_id).where(CourseMember.course_id == course_id,
                                                CourseMember.role == "student")
    learners = select(PathEnrollment.user_id).join(LearningPath).where(LearningPath.course_id == course_id)
    return select(User).where(User.role == "student", or_(User.id.in_(members), User.id.in_(learners)))


def identity(user):
    return {"user_id": user.id, "username": user.username, "full_name": user.full_name}


def fraction(summary):
    return summary["completed_count"] / summary["required_count"] if summary["required_count"] else 0


def class_rows(db, course_id, offset):
    paths = list(db.scalars(select(LearningPath).join(PathVersion, LearningPath.published_version_id == PathVersion.id).where(
        LearningPath.course_id == course_id, LearningPath.archived.is_(False), PathVersion.status == "published",
        select(PathStep.id).where(PathStep.path_version_id == PathVersion.id, PathStep.required.is_(True)).exists())))
    students = list(db.scalars(participants(db, course_id).order_by(User.full_name, User.username, User.id).offset(offset).limit(100)))
    enrolled = list(db.scalars(select(PathEnrollment).where(PathEnrollment.user_id.in_([s.id for s in students]),
                                                           PathEnrollment.path_id.in_([p.id for p in paths]))))
    loaded = enrollment_summaries(db, enrolled)
    by_student = {}
    for e in enrolled:
        by_student.setdefault(e.user_id, []).append(loaded[e.id])
    result = []
    for student in students:
        summaries = by_student.get(student.id, [])
        total = len(paths) - sum(s['required_count'] == 0 for s in summaries)
        summaries = [s for s in summaries if s['required_count']]
        result.append({**identity(student), "total_paths": total, "started_paths": len(summaries),
                       "completed_paths": sum(s["complete"] for s in summaries),
                       "progress": round(sum(fraction(s) for s in summaries) / total * 100, 2) if total else 0,
                       "elapsed_seconds": sum(s["elapsed_seconds"] for s in summaries)})
    return result


def report_path(db, user, path_id):
    path = db.get(LearningPath, path_id)
    if not path:
        raise HTTPException(404, "Learning path not found")
    course = course_access(db, user, path.course_id, edit=True)
    if not path.published_version_id:
        raise HTTPException(404, "Published path not found")
    return path, course


@router.get("/author/paths/{path_id}/progress")
def path_progress(path_id: str, offset: int = Query(default=0, ge=0),
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    path, course = report_path(db, user, path_id)
    rows = []
    students = list(db.scalars(participants(db, course.id).order_by(User.full_name, User.username, User.id).offset(offset).limit(100)))
    enrolled = list(db.scalars(select(PathEnrollment).where(PathEnrollment.path_id == path.id,
                                                           PathEnrollment.user_id.in_([s.id for s in students]))))
    loaded = enrollment_summaries(db, enrolled)
    by_student = {e.user_id: loaded[e.id] for e in enrolled}
    for student in students:
        rows.append({**identity(student), "enrollment": by_student.get(student.id)})
    version = db.get(PathVersion, path.published_version_id)
    audit(db, user, "learning.path_progress_read", path.id)
    db.commit()
    return {"path_id": path.id, "title": version.title, "course_id": course.id, "course_title": course.title,
            "archived": path.archived or course.archived, "participants": rows}


@router.get("/author/paths/{path_id}/participants/{user_id}")
def participant_work(path_id: str, user_id: str, offset: int = Query(default=0, ge=0),
                     user: User = Depends(current_user), db: Session = Depends(get_db)):
    from app.main import serialize_submission

    path, course = report_path(db, user, path_id)
    student = db.scalar(participants(db, course.id).where(User.id == user_id))
    if not student:
        raise HTTPException(404, "Participant not found")
    enrollment = db.scalar(select(PathEnrollment).where(PathEnrollment.path_id == path.id, PathEnrollment.user_id == student.id))
    summary = enrollment_summary(db, enrollment) if enrollment else None
    rows = []
    if enrollment:
        query = select(Submission, Attempt, PathStep).join(Attempt, Attempt.submission_id == Submission.id).join(
            PathStep, Submission.path_step_id == PathStep.id).where(
            Submission.enrollment_id == enrollment.id, Submission.owner_id == student.id,
            PathStep.path_version_id == enrollment.path_version_id).order_by(Submission.created_at.desc(), Submission.id).offset(offset).limit(100)
        rows = [{**serialize_submission(s, a), "step_title": step.title} for s, a, step in db.execute(query)]
    audit(db, user, "learning.participant_work_read", path.id, participant_id=student.id)
    db.commit()
    return {"participant": identity(student), "enrollment": summary, "submissions": rows,
            "path_id": path.id, "title": db.get(PathVersion, path.published_version_id).title,
            "course_id": course.id, "course_title": course.title, "archived": course.archived}
