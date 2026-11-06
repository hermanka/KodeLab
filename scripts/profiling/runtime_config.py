"""Capture only non-secret live benchmark settings, and reject a mismatched worker pool."""
import json
from pathlib import Path
import sys

sys.path.insert(0, "/app")

if "--preflight" in sys.argv:
    from sqlalchemy import func, select
    from app.db import session
    from app.models import Attempt, ValidationJob
    with session() as db:
        counts = {model.__name__: db.scalar(select(func.count()).select_from(model).where(
            model.state.in_(["queued", "running", "retry_pending"]))) for model in (Attempt, ValidationJob)}
    print(json.dumps({"pending_jobs_before_test": counts}))
    assert not any(counts.values()), "Existing jobs must finish before benchmark service restarts"
elif "--runner" in sys.argv:
    from runner.main import slot_count
    print(json.dumps({"runner_slots": slot_count}))
else:
    from app.tasks import celery
    expected = int(sys.argv[1])
    inspector = celery.control.inspect(timeout=10)
    pools = inspector.stats() or {}
    queues = inspector.active_queues() or {}
    workers = [{"node": node, "concurrency": value.get("pool", {}).get("max-concurrency"),
                "process_count": len(value.get("pool", {}).get("processes", [])),
                "queues": [q["name"] for q in queues.get(node, [])]} for node, value in pools.items()]
    assert any(w["concurrency"] == expected and w["process_count"] == expected and "celery" in w["queues"]
               for w in workers), f"Unexpected execution worker capacity: {workers}"
    result = {"workers": workers,
              "dispatch_interval_seconds": celery.conf.beat_schedule["dispatch-persistent-jobs"]["schedule"]}
    Path("/results/runtime-config.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
