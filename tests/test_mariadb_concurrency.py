"""Run only against the disposable MariaDB started by scripts/test-mariadb-concurrency.ps1."""
import os
import threading
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, update

from app.auth import hasher
from app.config import database_url
from app.db import engine, session
from app.main import app
from app.models import Attempt, Base, Course, QuotaLock, Submission, User
from app.providers import CustomProvider
from app.seed import seed
from tests.test_accounts_content import PASSWORD
from tests.test_learning import setup_path, enroll, read_all, submission_body

pytestmark = pytest.mark.skipif(not os.getenv('AUDIT_MYSQL_HOST'), reason='Requires disposable MariaDB test container')


def test_plugin_migration_resumes_partial_mariadb_upgrade(monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect, text
    from app.models import JudgePlugin, JudgePluginVersion

    assert os.environ['DB_HOST'] == os.environ['AUDIT_MYSQL_HOST']
    assert os.environ['DB_NAME'] == 'audit_fix_tests'
    monkeypatch.delenv('SQLITE_URL', raising=False)
    database_url.cache_clear()
    engine.cache_clear()
    config = Config('alembic.ini')
    command.upgrade(config, '0007')
    # Reproduce committed DDL before an interrupted upgrade, without deleting anything.
    JudgePlugin.__table__.create(engine())
    JudgePluginVersion.__table__.create(engine())
    with engine().begin() as connection:
        connection.execute(text('ALTER TABLE problem_versions ADD COLUMN provider_revision VARCHAR(64)'))
    command.upgrade(config, 'head')
    assert any(c['name'] == 'provider_revision' for c in inspect(engine()).get_columns('problem_validation_jobs'))
    command.upgrade(config, 'head')
    command.check(config)


def test_replay_waits_for_admission_without_locking_course(monkeypatch):
    assert os.environ['DB_HOST'] == os.environ['AUDIT_MYSQL_HOST']
    assert os.environ['DB_NAME'] == 'audit_fix_tests'
    monkeypatch.delenv('SQLITE_URL', raising=False)
    database_url.cache_clear()
    engine.cache_clear()
    Base.metadata.create_all(engine())
    seed()
    monkeypatch.setattr(CustomProvider, 'health_check', lambda self: True)
    with session() as db, db.begin():
        db.add(User(username='audit_admin', password_hash=hasher.hash(PASSWORD), role='admin'))
    with TestClient(app) as admin:
        login = admin.post('/auth/login', json={'username': 'audit_admin', 'password': PASSWORD})
        assert login.status_code == 200
        admin.headers['Authorization'] = 'Bearer ' + login.json()['access_token']
        teacher, student, cid, path, problem, _ = setup_path(admin, monkeypatch)
        e = enroll(student, path)
        read_all(student, e)
        body = submission_body(e, problem)
        original = student.post('/submissions', json=body).json()
        reached_admission = threading.Event()
        watching = threading.Event()
        outcomes = {}

        def observe(connection, cursor, statement, parameters, context, many):
            if watching.is_set() and 'FROM quota_locks' in statement and 'FOR UPDATE' in statement:
                reached_admission.set()

        def request(name, viewer, url, payload):
            try:
                outcomes[name] = viewer.post(url, json=payload).status_code
            except Exception as exc:
                outcomes[name] = type(exc).__name__

        replay = threading.Thread(name='audit-replay', target=request, args=(
            'replay', teacher, f"/author/submissions/{original['id']}/run", {'input': '2 3'}))
        submission = threading.Thread(name='audit-submission', target=request, args=('submission', student, '/submissions', body))
        event.listen(engine(), 'before_cursor_execute', observe)
        try:
            with session() as blocker, blocker.begin():
                blocker.scalar(select(QuotaLock).where(QuotaLock.id == 'admission').with_for_update())
                watching.set()
                replay.start()
                assert reached_admission.wait(5), 'Replay did not reach admission'
                # NOWAIT fails immediately if replay took Course first (the original deadlock).
                with session() as probe, probe.begin():
                    assert probe.scalar(select(Course).where(Course.id == cid).with_for_update(nowait=True))
                submission.start()
        finally:
            replay.join(timeout=15)
            if submission.ident is not None:
                submission.join(timeout=15)
            event.remove(engine(), 'before_cursor_execute', observe)
        assert not replay.is_alive() and not submission.is_alive()
        assert outcomes == {'replay': 202, 'submission': 202}
    engine().dispose()


@pytest.fixture
def mariadb_admin(monkeypatch):
    assert os.environ['DB_HOST'] == os.environ['AUDIT_MYSQL_HOST']
    assert os.environ['DB_NAME'] == 'audit_fix_tests'
    monkeypatch.delenv('SQLITE_URL', raising=False)
    database_url.cache_clear()
    engine.cache_clear()
    Base.metadata.create_all(engine())
    seed()
    monkeypatch.setattr(CustomProvider, 'health_check', lambda self: True)
    username = 'admission_' + uuid4().hex[:12]
    with session() as db, db.begin():
        db.add(User(username=username, password_hash=hasher.hash(PASSWORD), role='admin'))
    with TestClient(app) as client:
        login = client.post('/auth/login', json={'username': username, 'password': PASSWORD})
        assert login.status_code == 200
        client.headers['Authorization'] = 'Bearer ' + login.json()['access_token']
        yield client
    engine().dispose()
    engine.cache_clear()


def test_concurrent_admission_preserves_global_quota_and_idempotency(mariadb_admin):
    uid = mariadb_admin.get('/auth/me').json()['id']
    fillers = []
    pending = ['queued', 'running', 'retry_pending']
    body = {'language': 'c17', 'source': 'int main(){}'}
    try:
        with session() as db, db.begin():
            count = db.scalar(select(func.count()).select_from(Attempt).where(Attempt.state.in_(pending)))
            assert count < 49
            for _ in range(49-count):
                row = Submission(problem_version_id='sum-v1', language='c17', source='int main(){}',
                                 mode='judge', request_hash='isolated-quota-test')
                db.add(row)
                db.flush()
                fillers.append(row.id)
                db.add(Attempt(submission_id=row.id, provider='custom', snapshot={}))

        def burst(keys):
            gate = threading.Barrier(len(keys))
            responses = []
            def send(key):
                gate.wait(timeout=5)
                responses.append(mariadb_admin.post('/submissions', json=body, headers={'Idempotency-Key': key}))
            threads = [threading.Thread(target=send, args=(key,)) for key in keys]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=15)
                assert not thread.is_alive()
            assert len(responses) == len(keys)
            return responses

        assert sorted(r.status_code for r in burst([str(uuid4()), str(uuid4())])) == [202, 429]
        with session() as db, db.begin():
            assert db.scalar(select(func.count()).select_from(Attempt).where(Attempt.state.in_(pending))) == 50
            db.execute(update(Attempt).where(Attempt.submission_id.in_(
                select(Submission.id).where(Submission.owner_id == uid))).values(state='completed'))
        key = str(uuid4())
        responses = burst([key, key])
        assert [r.status_code for r in responses] == [202, 202]
        assert len({r.json()['id'] for r in responses}) == 1
        with session() as db:
            assert db.scalar(select(func.count()).select_from(Attempt).where(Attempt.state.in_(pending))) == 50
    finally:
        with session() as db, db.begin():
            db.execute(update(Attempt).where(Attempt.submission_id.in_(
                select(Submission.id).where((Submission.owner_id == uid) | Submission.id.in_(fillers)))).values(state='completed'))
