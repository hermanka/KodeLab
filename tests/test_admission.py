from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import engine, session
from app.models import Course, CourseMember, Submission, User
from app.providers import CustomProvider
from tests.test_api_tasks import client
from tests.test_learning import setup_path, enroll, read_all, submission_body


def test_preflight_releases_database_and_uses_no_write_locks(client, monkeypatch):
    _, student, _, path, problem, _ = setup_path(client, monkeypatch)
    enrollment = enroll(student, path)
    read_all(student, enrollment)
    phases = []
    scalar = Session.scalar

    def observe(db, statement, *args, **kwargs):
        if getattr(statement, '_for_update_arg', None) is not None:
            assert phases == ['health', 'prepare'], 'Write lock acquired before external preparation'
        return scalar(db, statement, *args, **kwargs)

    def health(provider):
        assert engine().pool.checkedout() == 0
        phases.append('health')
        return True

    def prepare(provider, problem_id):
        assert engine().pool.checkedout() == 0
        phases.append('prepare')

    monkeypatch.setattr(Session, 'scalar', observe)
    monkeypatch.setattr(CustomProvider, 'health_check', health)
    monkeypatch.setattr(CustomProvider, 'prepare_problem', prepare)
    assert student.post('/submissions', json=submission_body(enrollment, problem)).status_code == 202
    assert phases == ['health', 'prepare']


@pytest.mark.parametrize('change', ['archive', 'revoke', 'disable_user'])
def test_access_is_rechecked_after_health_check(client, monkeypatch, change):
    _, student, cid, path, problem, _ = setup_path(client, monkeypatch)
    enrollment = enroll(student, path)
    read_all(student, enrollment)
    uid = student.get('/auth/me').json()['id']

    def health(provider):
        with session() as db, db.begin():
            if change == 'archive':
                db.get(Course, cid).archived = True
            elif change == 'revoke':
                db.delete(db.get(CourseMember, (cid, uid)))
            else:
                db.get(User, uid).is_active = False
        return True

    monkeypatch.setattr(CustomProvider, 'health_check', health)
    result = student.post('/submissions', json=submission_body(enrollment, problem))
    assert result.status_code == (401 if change == 'disable_user' else 404)
    with session() as db:
        assert db.scalar(select(func.count()).select_from(Submission)) == 0


def test_idempotent_retry_succeeds_when_runner_is_offline(client, monkeypatch):
    headers = {'Idempotency-Key': str(uuid4())}
    body = {'language': 'c17', 'source': 'int main(){}'}
    first = client.post('/submissions', json=body, headers=headers)
    assert first.status_code == 202
    monkeypatch.setattr(CustomProvider, 'health_check', lambda provider: False)
    again = client.post('/submissions', json=body, headers=headers)
    assert again.status_code == 202 and again.json()['id'] == first.json()['id']
    assert client.post('/submissions', json=body).status_code == 503
    with session() as db:
        assert db.scalar(select(func.count()).select_from(Submission)) == 1


def test_provider_revision_change_during_preflight_cannot_admit_unchecked_provider(client, monkeypatch):
    import app.main as main
    revision = ['before']

    class Provider(CustomProvider):
        def __init__(self):
            self.revision = revision[0]
        def health_check(self):
            revision[0] = 'after'
            return True

    monkeypatch.setattr(main, 'provider_for', lambda *args, **kwargs: Provider())
    result = client.post('/submissions', json={'language': 'c17', 'source': 'int main(){}'})
    assert result.status_code == 409
    with session() as db:
        assert db.scalar(select(func.count()).select_from(Submission)) == 0
