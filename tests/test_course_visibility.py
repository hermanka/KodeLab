from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.db import session
from app.models import AuditEvent, Course, CourseMember, PathEnrollment, utcnow
from tests.test_api_tasks import client
from tests.test_accounts_content import account, course
from tests.test_learning import setup_path, enroll


@pytest.fixture(autouse=True)
def invite_secret(monkeypatch):
    monkeypatch.setenv('CLASS_INVITE_SECRET', 'isolated-invite-test-secret-with-64-characters-00000000000000000000')


def test_settings_change_visibility_without_resetting_members_or_progress(client, monkeypatch):
    teacher, student, cid, path, _, _ = setup_path(client, monkeypatch)
    e = enroll(student, path)
    student.post(f"/enrollments/{e['id']}/steps/{e['steps'][0]['id']}/complete")
    outsider, _ = account(client, 'visibility_outsider', 'student')
    assert outsider.get(f'/courses/{cid}/learning').status_code == 200
    settings = teacher.get(f'/courses/{cid}/settings').json()
    payload = {'title': 'Kelas baru', 'description': '<script>plain text</script>', 'is_public': False, 'edit_revision': settings['edit_revision']}
    response = teacher.patch(f'/courses/{cid}/settings', json=payload)
    assert response.status_code == 200
    assert response.json()['edit_revision'] == 2
    assert outsider.get(f'/courses/{cid}/learning').status_code == 404
    assert outsider.get(f'/courses/{cid}/leaderboard').status_code == 404
    assert outsider.get('/leaderboards').json()['rows'] == []
    after = student.get(f"/enrollments/{e['id']}").json()
    assert after['course_title'] == 'Kelas baru' and after['completed_count'] == 1
    assert after['path_version_id'] == e['path_version_id']
    assert student.get(f'/courses/{cid}/learning').json()['course']['description'] == payload['description']
    assert teacher.patch(f'/courses/{cid}/settings', json=payload).status_code == 409
    assert teacher.patch(f'/courses/{cid}/settings', json={**payload, 'edit_revision': 2, 'owner_id': 'fake'}).status_code == 422
    assert teacher.patch(f'/courses/{cid}/settings', json={**payload, 'edit_revision': 2, 'is_public': True}).status_code == 200
    assert outsider.get(f'/courses/{cid}/learning').status_code == 200


def test_invite_join_is_student_membership_idempotent_and_does_not_start_path(client):
    teacher, _ = account(client, 'invite_owner', 'teacher')
    student, user = account(client, 'invite_learner', 'student')
    cid = course(teacher)
    response = teacher.post(f'/courses/{cid}/invitation')
    assert response.status_code == 200
    code = response.json()['code']
    assert len(code) == 6 and code.isascii() and code.isdigit()
    assert student.get(f'/courses/{cid}/learning').status_code == 404
    for _ in range(2):
        joined = student.post('/courses/join', json={'code': code})
        assert joined.status_code == 200 and joined.json()['course_id'] == cid
    with session() as db:
        assert db.get(CourseMember, (cid, user['id'])).role == 'student'
        assert db.scalar(select(func.count()).select_from(PathEnrollment)) == 0
        assert db.get(Course, cid).invite_digest != code
        assert code not in str([event.details for event in db.scalars(select(AuditEvent))])
    assert student.get(f'/courses/{cid}/learning').status_code == 200
    assert 'invite_digest' not in str(student.get('/courses').json())
    assert teacher.get(f'/courses/{cid}/settings').json()['code'] == code
    with session() as db:
        assert db.get(Course, cid).invite_ciphertext != code
    # Using the invite must never downgrade an already assigned instructor.
    teacher.post(f'/courses/{cid}/members', json={'user_id': teacher.get('/auth/me').json()['id'], 'role': 'teacher'})
    assert teacher.post('/courses/join', json={'code': code}).status_code == 200
    with session() as db:
        assert db.get(CourseMember, (cid, teacher.get('/auth/me').json()['id'])).role == 'teacher'


def test_invite_rotation_revocation_expiry_and_archive(client):
    teacher, _ = account(client, 'rotation_owner', 'teacher')
    student, _ = account(client, 'rotation_student', 'student')
    cid = course(teacher)
    old = teacher.post(f'/courses/{cid}/invitation').json()['code']
    current = teacher.post(f'/courses/{cid}/invitation').json()['code']
    assert old != current
    assert student.post('/courses/join', json={'code': old}).status_code == 400
    with session() as db, db.begin():
        db.get(Course, cid).invite_expires_at = utcnow() - timedelta(seconds=1)
    assert student.post('/courses/join', json={'code': current}).status_code == 400
    code = teacher.post(f'/courses/{cid}/invitation').json()['code']
    teacher.post(f'/courses/{cid}/archive')
    assert student.post('/courses/join', json={'code': code}).status_code == 400
    assert teacher.post(f'/courses/{cid}/invitation').status_code == 409
    assert teacher.patch(f'/courses/{cid}/settings', json={'title': 'No', 'is_public': False, 'edit_revision': 1}).status_code == 409
    teacher.post(f'/courses/{cid}/restore')
    assert teacher.delete(f'/courses/{cid}/invitation').status_code == 200
    assert student.post('/courses/join', json={'code': code}).status_code == 400


def test_invite_public_switch_and_permission_boundaries(client):
    teacher, _ = account(client, 'settings_owner', 'teacher')
    assigned, instructor = account(client, 'settings_assigned', 'teacher')
    student, _ = account(client, 'settings_student', 'student')
    cid = course(teacher)
    teacher.post(f'/courses/{cid}/members', json={'user_id': instructor['id'], 'role': 'teacher'})
    for viewer in (assigned, student):
        assert viewer.get(f'/courses/{cid}/settings').status_code == 404
        assert viewer.patch(f'/courses/{cid}/settings', json={'title': 'No', 'edit_revision': 1}).status_code == 404
        assert viewer.post(f'/courses/{cid}/invitation').status_code == 404
        assert viewer.delete(f'/courses/{cid}/invitation').status_code == 404
    code = client.post(f'/courses/{cid}/invitation').json()['code']
    assert client.patch(f'/courses/{cid}/settings', json={'title': 'Public', 'is_public': True, 'edit_revision': 1}).status_code == 200
    assert student.post('/courses/join', json={'code': code}).status_code == 400
    assert teacher.post(f'/courses/{cid}/invitation').status_code == 409
    with session() as db:
        assert db.get(Course, cid).invite_digest is None


def test_invite_rate_limit_persists_after_failed_guesses(client):
    student, _ = account(client, 'invite_guesses', 'student')
    for _ in range(5):
        assert student.post('/courses/join', json={'code': '000000'}).status_code == 400
    assert student.post('/courses/join', json={'code': '000000'}).status_code == 429
    for code in ('12345', '1234567', 'abcdef', '１２３４５６'):
        assert student.post('/courses/join', json={'code': code}).status_code == 422


def test_invite_collisions_and_leading_zero_codes(client, monkeypatch):
    teacher, _ = account(client, 'collision_owner', 'teacher')
    student, _ = account(client, 'collision_student', 'student')
    first, second = course(teacher), course(teacher)
    values = iter([123456, 123456, 1])
    monkeypatch.setattr('app.course_settings.secrets.randbelow', lambda n: next(values))
    teacher.post(f'/courses/{first}/invitation')
    response = teacher.post(f'/courses/{second}/invitation')
    assert response.json()['code'] == '000001'
    assert student.post('/courses/join', json={'code': '000001'}).json()['course_id'] == second
