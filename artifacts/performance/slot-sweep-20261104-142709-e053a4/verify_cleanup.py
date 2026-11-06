"""Read-only fixture verification; run with /history and this directory mounted at /results."""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, "/app")
from sqlalchemy import func, select
from app.db import session
from app.models import Attempt, Course, User, ValidationJob
from app.tasks import celery

directory = Path("/results")
manifest = json.loads((directory/"manifest.json").read_text(encoding="utf-8-sig"))
prefixes = [json.loads((Path("/history")/r["directory"]/"results.json").read_text())["summary"]["run_id"]
            for r in manifest["runs"]]
assert len(set(prefixes)) == len(prefixes) == 2
names = [f"{prefix}_{i:02d}" for prefix in prefixes for i in range(30)]
with session() as db:
    users = db.scalars(select(User).where(User.username.in_(names))).all()
    result = {"attempts": len(prefixes), "fixture_accounts": len(users),
        "fixture_accounts_disabled": sum(not user.is_active for user in users),
        "fixture_classes_remaining": db.scalar(select(func.count()).select_from(Course).where(
            Course.title.in_(["Performance 30 users "+p for p in prefixes]))),
        "pending_jobs": {m.__name__: db.scalar(select(func.count()).select_from(m).where(
            m.state.in_(["queued", "running", "retry_pending"]))) for m in (Attempt, ValidationJob)}}
stats = celery.control.inspect(timeout=10).stats()
result["worker_pool_concurrency"] = sorted(p["pool"]["max-concurrency"] for p in stats.values())
result["dispatch_interval_seconds"] = celery.conf.beat_schedule["dispatch-persistent-jobs"]["schedule"]
result["verification_process_profiling_enabled"] = bool(os.getenv("JUDGE_PROFILE_DIR"))
assert result["fixture_accounts"] == result["fixture_accounts_disabled"] == 30*len(prefixes)
assert result["fixture_classes_remaining"] == 0 and not any(result["pending_jobs"].values())
assert result["worker_pool_concurrency"] == [1, 50] and result["dispatch_interval_seconds"] == 1
(directory/"verification-database.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
