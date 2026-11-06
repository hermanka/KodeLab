"""Run existing services with timing wrappers; production source remains untouched."""
from contextvars import ContextVar
from datetime import datetime
from functools import wraps
import json
import os
import sys

sys.path.insert(0, "/app")
import timing as t

db_depth = ContextVar("profile_db_depth", default=0)


def wrap(owner, attribute, name, after=None):
    original = getattr(owner, attribute)

    @wraps(original)
    def measured(*args, **kwargs):
        if not t.current.get():
            return original(*args, **kwargs)
        with t.span(name):
            result = original(*args, **kwargs)
            if after:
                after(result, args, kwargs)
            return result
    setattr(owner, attribute, measured)


def database():
    from sqlalchemy import event
    from sqlalchemy.orm import Session, SessionTransaction

    def wrap_db(attribute):
        original = getattr(Session, attribute)

        @wraps(original)
        def measured(self, *args, **kwargs):
            if not t.current.get() or db_depth.get():
                return original(self, *args, **kwargs)
            token = db_depth.set(1)
            name = "db."+attribute
            if args and attribute in ("scalar", "execute"):
                table = getattr(getattr(args[0], "table", None), "name", None)
                descriptions = getattr(args[0], "column_descriptions", [])
                entity = descriptions[0].get("entity") if descriptions else None
                if getattr(entity, "__tablename__", None) == "quota_locks":
                    name = "db.admission_lock"
                if table == "judging_attempts":
                    name = "db.attempt_update"
            try:
                with t.span(name):
                    return original(self, *args, **kwargs)
            finally:
                db_depth.reset(token)
        setattr(Session, attribute, measured)

    for method in ("scalar", "scalars", "execute", "flush", "commit"):
        wrap_db(method)
    wrap(SessionTransaction, "commit", "db.transaction_commit")

    @event.listens_for(Session, "after_commit")
    def committed(db):
        if t.current.get():
            t.event("db.committed")


def provider():
    from plugin.custom.provider import CustomProvider
    wrap(CustomProvider, "health_check", "provider.health")
    wrap(CustomProvider, "submit", "worker.runner_http")


def api():
    import app.main as main
    import uvicorn
    original = main.create_submission

    @wraps(original)
    def create(request, mode, db, key, user, **kwargs):
        with t.trace(key or "no-key", mode=mode):
            with t.span("api.create_submission"):
                row = original(request, mode, db, key, user, **kwargs)
                t.event("api.job", attempt_id=row["attempt_id"], submission_id=row["id"])
                return row
    main.create_submission = create
    database(); provider()
    uvicorn.run(main.app, host="0.0.0.0", port=8000)


def celery_service(kind):
    import app.tasks as tasks
    from celery import current_task
    from celery.signals import before_task_publish, after_task_publish
    publishes = {}

    @before_task_publish.connect(weak=False)
    def before(sender=None, headers=None, body=None, **kwargs):
        if sender not in ("judgement.dispatch", "judgement.run"):
            return
        identifier = headers["id"]
        trace_id = body[0][0] if sender == "judgement.run" else identifier
        publishes[identifier] = trace_id
        t.event("celery.publish_start", trace=str(trace_id), task=sender, task_id=identifier)

    @after_task_publish.connect(weak=False)
    def after(sender=None, headers=None, **kwargs):
        identifier = (headers or {}).get("id")
        trace_id = publishes.pop(identifier, None)
        if trace_id:
            t.event("celery.publish_end", trace=str(trace_id), task=sender, task_id=identifier)

    def task_wrap(task, label):
        original = task.run

        @wraps(original)
        def measured(*args, **kwargs):
            identifier = args[0] if args else current_task.request.id
            with t.trace(identifier, task_id=current_task.request.id):
                with t.span(label):
                    return original(*args, **kwargs)
        task.run = measured
    task_wrap(tasks.run_attempt, "worker.total")
    task_wrap(tasks.dispatch, "dispatch.batch")
    wrap(tasks, "public_result", "worker.validate_result")
    database(); provider()
    arguments = sys.argv[2:]
    if not arguments:
        raise ValueError("Pass the actual Compose Celery command arguments to the profiler")
    tasks.celery.start(arguments)


def runner():
    from docker.models.containers import Container, ContainerCollection
    from runner.engine import DockerRunner
    import runner.engine as engine
    import runner.main as main
    import uvicorn
    original_judge, original_execute = DockerRunner.judge, DockerRunner.execute

    @wraps(original_judge)
    def judge(self, request):
        with t.trace(request.attempt_id, mode=request.mode, language=request.language) as context:
            context["case_counter"] = 0
            with t.span("runner.total"):
                return original_judge(self, request)

    @wraps(original_execute)
    def execute(self, sandbox, phase, *args, **kwargs):
        context = t.current.get()
        if phase == "run":
            context["case_counter"] += 1
        with t.fields(phase=phase, case_index=context["case_counter"], exit_recorded=False,
                      container_id=getattr(sandbox, "id", None)):
            with t.span("runner.execute"):
                result = original_execute(self, sandbox, phase, *args, **kwargs)
                if phase == "compile" and not result.code:
                    try:
                        profile = json.loads(result.stdout).get("_compiler_profile")
                        if profile:
                            t.event("sandbox.compiler", **profile)
                    except ValueError:
                        pass
                return result
    DockerRunner.judge, DockerRunner.execute = judge, execute
    wrap(engine, "tokens_equal", "runner.check_output")

    def inspected(result, args, kwargs):
        context = t.current.get()
        state = args[0].attrs.get("State", {})
        if state.get("Status") == "exited" and not context["fields"].get("exit_recorded"):
            context["fields"]["exit_recorded"] = True
            started, finished = state.get("StartedAt"), state.get("FinishedAt")
            if started and finished:
                seconds = (datetime.fromisoformat(finished.replace("Z", "+00:00"))-
                           datetime.fromisoformat(started.replace("Z", "+00:00"))).total_seconds()
                t.event("sandbox.pid1_lifetime", duration_ms=seconds*1000,
                        started_at=started, finished_at=finished, exit_code=state.get("ExitCode"))

    wrap(ContainerCollection, "create", "runner.container_create",
         after=lambda result, args, kwargs: t.event("sandbox.created", container_id=result.id))
    for method, name in (("attach_socket", "runner.attach_stdin"), ("start", "runner.container_start"),
                         ("attach", "runner.attach_output"), ("reload", "runner.inspect"),
                         ("wait", "runner.container_wait"), ("remove", "runner.container_remove"),
                         ("update", "runner.update_limits")):
        wrap(Container, method, name, after=inspected if method == "reload" else None)
    uvicorn.run(main.app, host="0.0.0.0", port=8001)


if __name__ == "__main__":
    component = sys.argv[1]
    if component == "api": api()
    elif component == "runner": runner()
    else: celery_service(component)
