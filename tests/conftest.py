import pytest


@pytest.fixture(autouse=True)
def no_broker(monkeypatch):
    """API submissions publish to Celery after commit; unit tests have no Redis."""
    from app.tasks import run_attempt
    sent = []
    monkeypatch.setattr(run_attempt, "apply_async", lambda args, **kwargs: sent.append(args[0]))
    return sent
