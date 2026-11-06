from fastapi.testclient import TestClient
from datetime import timedelta
import importlib
from uuid import uuid4
from sqlalchemy import select

from app.auth import hasher
from app.db import session
from app.main import app
from app.models import AuditEvent, Course, CourseMember, User, utcnow
from tests.test_api_tasks import client
from tests.test_accounts_content import account, course, PASSWORD
from tests.test_learning import setup_path, enroll, read_all, submission_body


def test_registration_and_profile_update_require_name_email_and_reject_privilege_fields(client):
    guest = TestClient(app)
    body = {'username': 'new_profile', 'password': PASSWORD}
    assert guest.post('/auth/register', json=body).status_code == 422
    assert guest.post('/auth/register', json={**body, 'full_name': 'Name', 'email': 'invalid'}).status_code == 422
    data = {**body, 'full_name': 'New Student', 'email': 'NEW@example.test'}
    assert guest.post('/auth/register', json={**data, 'role': 'admin'}).status_code == 422
    registered = guest.post('/auth/register', json=data)
    assert registered.status_code == 201 and registered.json()['email'] == 'new@example.test'
    guest.post('/auth/login', json=body)
    csrf = guest.cookies['judgement_csrf']
    profile = {'full_name': 'Updated Name', 'email': 'updated@example.test'}
    assert guest.patch('/auth/profile', json=profile).status_code == 403
    headers = {'X-CSRF-Token': csrf}
    updated = guest.patch('/auth/profile', json=profile, headers=headers)
    assert updated.status_code == 200 and updated.json()['full_name'] == 'Updated Name'
    assert updated.json()['username'] == body['username']
    assert guest.patch('/auth/profile', json={**profile, 'role': 'admin'}, headers=headers).status_code == 422
    assert guest.patch('/auth/profile', json={**profile, 'username': 'changed'}, headers=headers).status_code == 422
    other, _ = account(client, 'other_profile', 'student')
    assert other.patch('/auth/profile', json=profile).status_code == 409


def test_password_change_checks_current_password_and_revokes_all_sessions(client):
    student, user = account(client, 'password_student', 'student')
    other = TestClient(app)
    other.post('/auth/login', json={'username': 'password_student', 'password': PASSWORD})
    new = 'new-password-long-enough-for-testing'
    assert student.post('/auth/password', json={'current_password': 'incorrect', 'new_password': new}).status_code == 400
    assert student.get('/auth/me').status_code == 200
    assert student.post('/auth/password', json={'current_password': PASSWORD, 'new_password': new}).status_code == 200
    assert student.get('/auth/me').status_code == 401
    assert other.get('/auth/me').status_code == 401
    assert other.post('/auth/login', json={'username': 'password_student', 'password': PASSWORD}).status_code == 401
    assert other.post('/auth/login', json={'username': 'password_student', 'password': new}).status_code == 200
    with session() as db:
        assert hasher.verify(db.get(User, user['id']).password_hash, new)
        assert new not in str([a.details for a in db.scalars(select(AuditEvent))])


def test_public_auto_membership_cannot_bypass_private_class_or_archives(client, monkeypatch):
    monkeypatch.setenv('CLASS_INVITE_SECRET', 'isolated-private-access-invite-secret-for-unit-test')
    teacher, assigned, cid, path, problem, _ = setup_path(client, monkeypatch)
    visitor, visitor_user = account(client, 'public_visitor', 'student')
    e = enroll(visitor, path)
    read_all(visitor, e)
    body = submission_body(e, problem)
    retry_headers = {'Idempotency-Key': str(uuid4())}
    first = visitor.post('/submissions', json=body, headers=retry_headers)
    assert first.status_code == 202
    with session() as db:
        assert db.get(CourseMember, (cid, visitor_user['id'])).access_source == 'public'
    settings = teacher.get(f'/courses/{cid}/settings').json()
    teacher.patch(f'/courses/{cid}/settings', json={'title': settings['title'], 'is_public': False, 'edit_revision': 1})
    for url in (f'/courses/{cid}/learning', f'/courses/{cid}/leaderboard', f"/enrollments/{e['id']}"):
        assert visitor.get(url).status_code == 404
    assert cid not in [c['id'] for c in visitor.get('/courses').json()]
    assert visitor.post('/submissions', json=body, headers=retry_headers).status_code == 404
    assert visitor.get(f"/submissions/{first.json()['id']}").status_code == 404
    assert visitor.get('/submissions').json() == []
    assert assigned.get(f'/courses/{cid}/learning').status_code == 200
    code = teacher.post(f'/courses/{cid}/invitation').json()['code']
    assert visitor.post('/courses/join', json={'code': code}).status_code == 200
    assert visitor.get(f"/enrollments/{e['id']}").status_code == 200
    assert visitor.post('/submissions', json=body, headers=retry_headers).json()['id'] == first.json()['id']
    row = visitor.get(f'/courses/{cid}/leaderboard').json()['rows'][0]
    assert 'full_name' in row and 'email' not in row
    teacher.post(f'/courses/{cid}/archive')
    assert visitor.get('/courses', params={'status': 'archived'}).json() == []
    assert visitor.get(f'/courses/{cid}/learning').status_code == 404
    assert assigned.get(f'/courses/{cid}/learning').status_code == 404
    assert visitor.post('/submissions', json=body, headers=retry_headers).status_code == 404
    assert teacher.get(f'/courses/{cid}/learning').status_code == 200
    assert client.get(f'/courses/{cid}/learning').status_code == 200


def test_legacy_revoked_assignment_does_not_become_private_access_again(client, monkeypatch):
    cid = course(client)
    owner = client.get('/auth/me').json()['id']
    now = utcnow().replace(microsecond=0)
    ids = [str(uuid4()) for _ in range(3)]
    with session() as db, db.begin():
        for index, uid in enumerate(ids):
            db.add(User(id=uid, username=f'legacy_rejoin_{index}', password_hash='unused'))
        db.flush()
        for uid in ids:
            db.add(CourseMember(course_id=cid, user_id=uid, access_source='assignment'))
            db.add(AuditEvent(actor_id=owner, action='course.member_assigned', object_id=cid, details={'user_id': uid}, created_at=now))
            db.add(AuditEvent(actor_id=owner, action='course.member_removed', object_id=cid, details={'user_id': uid}, created_at=now))
        db.add(AuditEvent(actor_id=owner, action='course.member_assigned', object_id=cid,
                          details={'user_id': ids[1]}, created_at=now + timedelta(seconds=5)))
        db.add(AuditEvent(actor_id=owner, action='course.member_assigned', object_id=cid,
                          details={'user_id': ids[2], 'access_source': 'assignment'}, created_at=now))
    migration = importlib.import_module('migrations.versions.0007_legacy_membership_revocations')
    with session() as db, db.begin():
        monkeypatch.setattr(migration.op, 'get_bind', lambda: db.connection())
        migration.upgrade()
        db.expire_all()
        assert db.get(CourseMember, (cid, ids[0])).access_source == 'public'
        assert db.get(CourseMember, (cid, ids[1])).access_source == 'assignment'
        assert db.get(CourseMember, (cid, ids[2])).access_source == 'assignment'
