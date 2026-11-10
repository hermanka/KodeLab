from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import database_url
from app.db import engine, session
from app.models import Attempt, Base, ProblemVersion, User, utcnow
from app.providers import CustomProvider, ProviderUnavailable
from app.seed import seed


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    database_url.cache_clear()
    engine.cache_clear()
    Base.metadata.create_all(engine())
    seed()
    from app.auth import hasher
    with session() as db, db.begin():
        db.add(User(username="test_admin", password_hash=hasher.hash("test-password-long-enough"), role="admin"))
    monkeypatch.setattr(CustomProvider, "health_check", lambda self: True)
    from app.main import app
    with TestClient(app) as client:
        login = client.post("/auth/login", json={"username": "test_admin", "password": "test-password-long-enough"})
        assert login.status_code == 200
        client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
        yield client
    engine().dispose()
    engine.cache_clear()
    database_url.cache_clear()


def test_sql_outbox_idempotency_and_provider_snapshot(client, monkeypatch):
    key = str(uuid4())
    body = {"language": "cpp17", "source": "int main(){}"}
    first = client.post("/submissions", json=body, headers={"Idempotency-Key": key})
    assert first.status_code == 202
    again = client.post("/submissions", json=body, headers={"Idempotency-Key": key})
    assert first.json()["id"] == again.json()["id"]
    assert client.post("/submissions", json={**body, "source": "bad"},
                       headers={"Idempotency-Key": key}).status_code == 409
    monkeypatch.setenv("DEFAULT_PROVIDER", "domjudge")
    row = client.get(f"/submissions/{first.json()['id']}").json()
    assert row["provider"] == "custom"
    assert client.post("/submissions", json=body).status_code == 422
    with session() as db:
        assert len(db.scalars(select(Attempt)).all()) == 1
        assert db.get(Attempt, row["attempt_id"]).snapshot["language"] == "cpp17"


def test_validation_and_private_cases(client):
    assert client.get("/problems", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert len(client.get("/problems").json()[0]["samples"]) == 1
    assert client.post("/submissions", json={"language": "c17", "source": "x"},
                       headers={"Idempotency-Key": "invalid"}).status_code == 422
    assert client.post("/submissions", json={"language": "cpp20", "source": "x"}).status_code == 422
    assert client.post("/submissions", content=b"x" * 2097153).status_code == 413
    with session() as db, db.begin():
        db.get(ProblemVersion, "sum-v1").scoring_policy = "partial-v1"
    assert client.post("/submissions", json={"language": "c17", "source": "x"}).status_code == 422


def test_provider_failure_retries_without_assigning_zero(client, monkeypatch):
    from app.tasks import run_attempt

    row = client.post("/submissions", json={"language": "c17", "source": "x"}).json()

    def unavailable(*args, **kwargs):
        raise ProviderUnavailable("offline")

    monkeypatch.setattr(CustomProvider, "submit", unavailable)
    for expected_state in ("retry_pending", "retry_pending", "system_error"):
        run_attempt.run(row["attempt_id"])
        response = client.get(f"/submissions/{row['id']}").json()
        assert response["state"] == expected_state
        assert response["score"] is None
        assert response["verdict"] is None


def test_duplicate_tasks_do_not_execute_running_or_finished_attempt(client, monkeypatch):
    from app.tasks import run_attempt

    row = client.post("/submissions", json={"language": "c17", "source": "x"}).json()
    with session() as db, db.begin():
        attempt = db.get(Attempt, row["attempt_id"])
        attempt.state = "running"
        attempt.lease_until = utcnow() + timedelta(seconds=180)

    def forbidden(*args, **kwargs):
        pytest.fail("duplicate task invoked the provider")

    monkeypatch.setattr(CustomProvider, "submit", forbidden)
    run_attempt.run(row["attempt_id"])
    with session() as db, db.begin():
        db.get(Attempt, row["attempt_id"]).state = "completed"
    run_attempt.run(row["attempt_id"])


def test_dispatch_recovers_orphaned_attempt_and_sql_queue(client, monkeypatch):
    from app.tasks import dispatch, run_attempt

    row = client.post("/submissions", json={"language": "c17", "source": "x"}).json()
    with session() as db, db.begin():
        attempt = db.get(Attempt, row["attempt_id"])
        attempt.state = "running"
        attempt.lease_until = utcnow() - timedelta(seconds=1)
        attempt.lease_token = str(uuid4())
    sent = []
    monkeypatch.setattr(run_attempt, "apply_async", lambda args, **kwargs: sent.append(args[0]))
    dispatch.run()
    assert sent == [row["attempt_id"]]
    with session() as db:
        attempt = db.get(Attempt, row["attempt_id"])
        assert attempt.state == "retry_pending"
        assert attempt.lease_token is None
        assert attempt.retries == 1


def test_submission_is_published_immediately_and_falls_back_to_scheduler(client, monkeypatch, no_broker):
    from app.tasks import dispatch, run_attempt

    row = client.post("/submissions", json={"language": "c17", "source": "x"}).json()
    assert no_broker == [row["attempt_id"]]
    dispatch.run()  # Already published: the scheduler must not send a duplicate right away.
    assert no_broker == [row["attempt_id"]]

    def broker_down(args, **kwargs):
        raise ConnectionError("redis offline")

    monkeypatch.setattr(run_attempt, "apply_async", broker_down)
    lost = client.post("/submissions", json={"language": "c17", "source": "y"})
    assert lost.status_code == 202
    sent = []
    monkeypatch.setattr(run_attempt, "apply_async", lambda args, **kwargs: sent.append(args[0]))
    dispatch.run()
    assert sent == [lost.json()["attempt_id"]]
