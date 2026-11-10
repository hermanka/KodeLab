from uuid import uuid4

from sqlalchemy import func, select

from app.db import session
from app.models import Submission
from app.providers import CustomProvider
from tests.test_api_tasks import client


def test_submission_is_queued_when_runner_is_offline(client, monkeypatch):
    # A busy or offline runner must not reject learners: the SQL attempt is dispatched and retried later.
    def unreachable(provider):
        raise AssertionError("Admission must not call the runner")

    monkeypatch.setattr(CustomProvider, 'health_check', unreachable)
    headers = {'Idempotency-Key': str(uuid4())}
    body = {'language': 'c17', 'source': 'int main(){}'}
    first = client.post('/submissions', json=body, headers=headers)
    assert first.status_code == 202
    again = client.post('/submissions', json=body, headers=headers)
    assert again.status_code == 202 and again.json()['id'] == first.json()['id']
    assert client.post('/submissions', json=body).status_code == 202
    with session() as db:
        assert db.scalar(select(func.count()).select_from(Submission)) == 2
