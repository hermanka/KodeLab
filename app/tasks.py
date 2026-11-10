import logging
import os
from datetime import timedelta
from uuid import UUID, uuid5

from celery import Celery
from sqlalchemy import select, update

from app.contracts import Case, JudgeRequest
from app.db import session
from app.judging import public_result
from app.models import (Attempt, AuditEvent, ProblemVersion, ReferenceSolution, Submission,
                        TestCase, ValidationJob, new_id, utcnow)
from app.providers import provider_for

logger = logging.getLogger(__name__)
celery = Celery("judgement", broker=os.getenv("REDIS_URL", "redis://redis:6379/0"))
celery.conf.update(
    task_serializer="json", accept_content=["json"], task_ignore_result=True,
    task_acks_late=True, task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True, worker_prefetch_multiplier=1,
    # Fail fast when Redis is unreachable: the API publishes inline and must not hang (21 s -> 1 s measured).
    broker_transport_options={"visibility_timeout": 480, "socket_connect_timeout": 1, "max_retries": 0},
    beat_schedule={"dispatch-persistent-jobs": {"task": "judgement.dispatch", "schedule": 1.0}},
    timezone="UTC",
    task_routes={"judgement.validate": {"queue": "validation"}},
)


@celery.task(name="judgement.dispatch")
def dispatch():
    now = utcnow()
    with session() as db, db.begin():
        stale = db.scalars(select(Attempt).where(
            Attempt.state == "running", Attempt.lease_until < now,
        ).with_for_update(skip_locked=True)).all()
        for attempt in stale:
            attempt.retries += 1
            attempt.state = "retry_pending" if attempt.retries <= 2 else "system_error"
            attempt.error_code = "worker_lease_expired"
            attempt.lease_token = None
            attempt.dispatch_after = now
        rows = db.scalars(select(Attempt).where(
            Attempt.state.in_(["queued", "retry_pending"]), Attempt.dispatch_after <= now,
        ).limit(20).with_for_update(skip_locked=True)).all()
        for attempt in rows:
            # A crash after publishing can redeliver: run_attempt claims a SQL lease.
            run_attempt.apply_async(args=[attempt.id], retry=False)
            attempt.dispatch_after = now + timedelta(seconds=30)
        stale_validations = db.scalars(select(ValidationJob).where(
            ValidationJob.state == "running", ValidationJob.lease_until < now,
        ).with_for_update(skip_locked=True)).all()
        for job in stale_validations:
            job.retries += 1
            job.state = "retry_pending" if job.retries <= 2 else "system_error"
            job.lease_token, job.lease_until = None, None
            job.error_code, job.dispatch_after = "worker_lease_expired", now
            if job.state == "system_error":
                db.execute(update(ProblemVersion).where(
                    ProblemVersion.id == job.problem_version_id, ProblemVersion.validation_job_id == job.id,
                    ProblemVersion.status == "validating",
                ).values(status="draft"))
        validations = db.scalars(select(ValidationJob).where(
            ValidationJob.state.in_(["queued", "retry_pending"]), ValidationJob.dispatch_after <= now,
        ).limit(5).with_for_update(skip_locked=True)).all()
        for job in validations:
            run_validation.apply_async(args=[job.id], queue="validation", retry=False)
            job.dispatch_after = now + timedelta(seconds=30)


def publish_attempt(attempt_id):
    """Immediate best-effort dispatch after the API commit; dispatch() stays the fallback for every failure."""
    try:
        run_attempt.apply_async(args=[attempt_id], retry=False)
    except Exception as exc:
        logger.warning("Immediate dispatch failed attempt=%s category=%s", attempt_id, type(exc).__name__)
        with session() as db, db.begin():
            db.execute(update(Attempt).where(Attempt.id == attempt_id, Attempt.state == "queued")
                       .values(dispatch_after=utcnow()))


@celery.task(name="judgement.run", soft_time_limit=165, time_limit=175)
def run_attempt(attempt_id):
    token = new_id()
    with session() as db, db.begin():
        claimed = db.execute(update(Attempt).where(
            Attempt.id == attempt_id, Attempt.state.in_(["queued", "retry_pending"]),
        ).values(state="running", lease_token=token,
                 lease_until=utcnow() + timedelta(seconds=180)))
        if claimed.rowcount != 1:
            return
    try:
        with session() as db:
            attempt = db.get(Attempt, attempt_id)
            submission = db.get(Submission, attempt.submission_id)
            snapshot = attempt.snapshot
            if submission.mode == "run":
                cases = [Case(id="custom-input", input=submission.custom_input or "", public=True)]
            else:
                cases = [Case(id=t.id, input=t.input, expected=t.expected, public=t.public)
                         for t in db.scalars(select(TestCase).where(
                             TestCase.problem_version_id == snapshot["problem_version_id"],
                         ).order_by(TestCase.position))]
            request = JudgeRequest(attempt_id=attempt.id, language=snapshot["language"],
                                   source=submission.source, mode=submission.mode,
                                   checker=snapshot["checker"], limits=snapshot["limits"], cases=cases)
            provider = provider_for(attempt.provider, revision=snapshot.get("provider_revision"), execution=True, db=db)
        reference = provider.submit(request, attempt_id)
        result = provider.get_result(reference)
        public = public_result(result, cases, request.mode)
        with session() as db, db.begin():
            changed = db.execute(update(Attempt).where(Attempt.id == attempt_id, Attempt.lease_token == token).values(
                state="completed", verdict=result.verdict, score=public["score"], result=public,
                error_code=None, finished_at=utcnow(), lease_token=None, lease_until=None,
            ))
            if changed.rowcount == 1:
                from app.learning import record_accepted_completion
                attempt = db.get(Attempt, attempt_id)
                submission = db.get(Submission, attempt.submission_id)
                record_accepted_completion(db, submission, attempt)
    except Exception as exc:
        # Log category/ID only. HTTP exceptions may contain internal addresses or payloads.
        logger.warning("Judging failed attempt=%s category=%s", attempt_id, type(exc).__name__)
        with session() as db, db.begin():
            attempt = db.scalar(select(Attempt).where(
                Attempt.id == attempt_id, Attempt.lease_token == token,
            ).with_for_update())
            if attempt:
                attempt.retries += 1
                attempt.state = "retry_pending" if attempt.retries <= 2 else "system_error"
                attempt.error_code = "provider_or_validation_error"
                attempt.dispatch_after = utcnow() + timedelta(seconds=10)
                attempt.lease_token = None
                attempt.lease_until = None


@celery.task(name="judgement.validate", soft_time_limit=330, time_limit=345)
def run_validation(job_id):
    token = new_id()
    with session() as db, db.begin():
        claimed = db.execute(update(ValidationJob).where(
            ValidationJob.id == job_id, ValidationJob.state.in_(["queued", "retry_pending"]),
        ).values(state="running", lease_token=token, lease_until=utcnow() + timedelta(seconds=360)))
        if claimed.rowcount != 1:
            return
    try:
        with session() as db:
            job = db.get(ValidationJob, job_id)
            version = db.get(ProblemVersion, job.problem_version_id)
            if version.edit_revision != job.edit_revision or version.validation_job_id != job.id:
                raise ValueError("Validation no longer matches draft")
            cases = [Case(id=t.id, input=t.input, expected=t.expected, public=t.public)
                     for t in db.scalars(select(TestCase).where(TestCase.problem_version_id == version.id).order_by(TestCase.position))]
            solutions = {r.language: r.source for r in db.scalars(select(ReferenceSolution).where(
                ReferenceSolution.problem_version_id == version.id))}
            if set(solutions) != set(version.languages):
                raise ValueError("Missing reference language")
            # The reference must pass within half the CPU limit: parallel load slows the same program ~2x.
            # shortcut: RLIMIT_CPU takes whole seconds, so a 1 s limit gets no margin; needs sub-second CPU timing to fix.
            limits = {**version.limits, "time_seconds": max(1, version.limits["time_seconds"] // 2)}
            requests = [JudgeRequest(attempt_id=uuid5(UUID(job.id), language), language=language,
                                     source=solutions[language], mode="judge", cases=cases,
                                     checker=version.checker, limits=limits) for language in version.languages]
            provider_name, provider_revision = job.provider, job.provider_revision
        results = {}
        for request in requests:
            provider = provider_for(provider_name, revision=provider_revision, execution=True)
            reference = provider.submit(request, str(request.attempt_id))
            result = provider.get_result(reference)
            public_result(result, cases, "judge")
            results[request.language] = result.model_dump(mode="json")
        valid = all(result["verdict"] == "ACCEPTED" for result in results.values())
        with session() as db, db.begin():
            job = db.scalar(select(ValidationJob).where(
                ValidationJob.id == job_id, ValidationJob.lease_token == token,
            ).with_for_update())
            if not job:
                return
            job.state, job.valid, job.result = "completed", valid, results
            job.error_code, job.lease_token, job.lease_until = None, None, None
            db.execute(update(ProblemVersion).where(
                ProblemVersion.id == job.problem_version_id, ProblemVersion.validation_job_id == job.id,
                ProblemVersion.edit_revision == job.edit_revision, ProblemVersion.status == "validating",
            ).values(status="draft"))
            db.add(AuditEvent(actor_id=job.actor_id, action="problem.validation_completed",
                              object_id=job.problem_version_id, details={"validation_job_id": job.id, "valid": valid}))
    except Exception as exc:
        logger.warning("Reference validation failed job=%s category=%s", job_id, type(exc).__name__)
        with session() as db, db.begin():
            job = db.scalar(select(ValidationJob).where(
                ValidationJob.id == job_id, ValidationJob.lease_token == token,
            ).with_for_update())
            if job:
                job.retries += 1
                job.state = "retry_pending" if job.retries <= 2 else "system_error"
                job.error_code = "provider_or_validation_error"
                job.dispatch_after = utcnow() + timedelta(seconds=10)
                job.lease_token, job.lease_until = None, None
                if job.state == "system_error":
                    db.execute(update(ProblemVersion).where(
                        ProblemVersion.id == job.problem_version_id, ProblemVersion.validation_job_id == job.id,
                        ProblemVersion.status == "validating",
                    ).values(status="draft"))
