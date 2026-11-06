import importlib
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from app.auth import digest
from app.db import engine, session
from app.main import app
from app.models import (Attempt, AuditEvent, AuthSession, Course, CourseMember, LearningPath, Lesson, LessonVersion,
                        PathEnrollment, PathStep, PathVersion, Submission, User, utcnow)
from app.tasks import run_attempt
from tests.test_api_tasks import client
from tests.test_accounts_content import account, course
from tests.test_learning import setup_path, enroll, read_all, stub_results, submission_body


def test_delete_body_limit_precedes_auth_and_validation(client):
    with TestClient(app) as anonymous:
        for viewer in (anonymous, client):
            response = viewer.request('DELETE', '/courses/not-a-real-class',
                                      json={'confirmation_title': 'x' * 2097153})
            assert response.status_code == 413


def test_replay_audit_failure_rolls_back_job_and_idempotency_is_audited_once(client, monkeypatch):
    teacher, student, cid, path, problem, _ = setup_path(client, monkeypatch)
    e = enroll(student, path)
    read_all(student, e)
    original = student.post('/submissions', json=submission_body(e, problem)).json()
    tid = teacher.get('/auth/me').json()['id']
    main = importlib.import_module('app.main')
    audit = main.audit
    def fail(*args, **kwargs):
        raise RuntimeError('injected audit failure')
    monkeypatch.setattr(main, 'audit', fail)
    url = f"/author/submissions/{original['id']}/run"
    with pytest.raises(RuntimeError, match='injected audit failure'):
        teacher.post(url, json={'input': '2 3'})
    with session() as db:
        assert db.scalar(select(func.count()).select_from(Submission).where(Submission.owner_id == tid)) == 0
        assert db.scalar(select(func.count()).select_from(Attempt)) == 1
    monkeypatch.setattr(main, 'audit', audit)
    headers = {'Idempotency-Key': str(uuid4())}
    first = teacher.post(url, json={'input': '2 3'}, headers=headers)
    assert first.status_code == 202
    assert teacher.post(url, json={'input': '2 3'}, headers=headers).json()['id'] == first.json()['id']
    with session() as db:
        rows = list(db.scalars(select(AuditEvent).where(AuditEvent.action == 'submission.instructor_run')))
        assert len(rows) == 1 and rows[0].details['run_id'] == first.json()['id']
    teacher.post(f'/courses/{cid}/archive')
    assert teacher.post(url, json={'input': '2 3'}, headers=headers).status_code == 409


def invitation_clients(count):
    tokens = []
    with session() as db, db.begin():
        for i in range(count):
            user = User(username=f'audit_invite_{i:03}', password_hash='not-used-for-login', role='student')
            db.add(user)
            db.flush()
            token = str(uuid4())
            tokens.append(token)
            db.add(AuthSession(token_hash=digest(token), user_id=user.id, csrf_hash=digest('unused'),
                               expires_at=utcnow() + timedelta(hours=1)))
    return tokens


def test_shared_ip_allows_classroom_join_but_stops_guessing_before_lookup(client, monkeypatch):
    monkeypatch.setenv('CLASS_INVITE_SECRET', 'isolated-audit-invitation-secret-long-enough')
    cid = course(client)
    code = client.post(f'/courses/{cid}/invitation').json()['code']
    tokens = invitation_clients(40)
    for token in tokens:
        with TestClient(app) as viewer:
            assert viewer.post('/courses/join', json={'code': code}, headers={'Authorization': 'Bearer ' + token}).status_code == 200
    wrong = '000000' if code != '000000' else '000001'
    for token in tokens[:30]:
        with TestClient(app) as viewer:
            assert viewer.post('/courses/join', json={'code': wrong}, headers={'Authorization': 'Bearer ' + token}).status_code == 400
    # A blocked IP cannot keep probing valid codes via a different response status.
    with TestClient(app) as viewer:
        assert viewer.post('/courses/join', json={'code': code}, headers={'Authorization': 'Bearer ' + tokens[-1]}).status_code == 429


def test_course_details_and_managed_pagination_do_not_depend_on_catalog_page(client):
    teacher, owner = account(client, 'page_teacher', 'teacher')
    student, _ = account(client, 'page_student', 'student')
    admin_id = client.get('/auth/me').json()['id']
    with session() as db, db.begin():
        for i in range(100):
            db.add(Course(id=f'000-public-{i:03}', owner_id=admin_id, title='Other public class', is_public=True))
        for i in range(101):
            db.add(Course(id=f'zzz-owned-{i:03}', owner_id=owner['id'], title=f'Owned {i}'))
    assert not any(c['id'].startswith('zzz') for c in teacher.get('/courses').json())
    first = teacher.get('/courses?managed=true').json()
    last = teacher.get('/courses?managed=true&offset=100').json()
    assert len(first) == 100 and all(c['can_manage'] for c in first)
    assert [c['id'] for c in last] == ['zzz-owned-100']
    detail = teacher.get('/courses/zzz-owned-100')
    assert detail.status_code == 200 and detail.json()['can_delete']
    assert 'code' not in detail.json() and 'invite_digest' not in detail.json()
    assert student.get('/courses/zzz-owned-100').status_code == 404
    assert student.get('/courses?managed=true').json() == []
    teacher.post('/courses/zzz-owned-100/archive')
    assert teacher.get('/courses/zzz-owned-100').json()['archived']
    assert student.get('/courses/zzz-owned-100').status_code == 404


def test_optional_only_draft_cannot_publish_and_legacy_reference_path_does_not_reduce_progress(client, monkeypatch):
    teacher, student, cid, path, _, payload = setup_path(client, monkeypatch)
    e = enroll(student, path)
    optional = teacher.post(f'/author/courses/{cid}/paths', json={**payload,
        'steps': [{**payload['steps'][0], 'required': False}]}).json()
    url = f"/author/path-versions/{optional['id']}/publish"
    assert teacher.post(url, json={'edit_revision': 1}).status_code == 422
    # Existing reference content is retained; it must not make an assigned path's progress unreachable.
    with session() as db, db.begin():
        db.get(PathVersion, optional['id']).status = 'published'
        db.get(LearningPath, optional['path_id']).published_version_id = optional['id']
    student.post(f"/enrollments/{e['id']}/steps/{e['steps'][0]['id']}/complete")
    row = teacher.get(f'/author/courses/{cid}/progress').json()[0]
    assert row['total_paths'] == 1 and row['progress'] == 33.33
    enroll(student, optional)
    revision = teacher.post(f"/author/paths/{optional['path_id']}/versions").json()
    update = {**payload, 'steps': [payload['steps'][0]], 'edit_revision': 1}
    assert teacher.put(f"/author/path-versions/{revision['id']}", json=update).status_code == 200
    assert teacher.post(f"/author/path-versions/{revision['id']}/publish", json={'edit_revision': 2}).status_code == 200
    row = teacher.get(f'/author/courses/{cid}/progress').json()[0]
    assert row['total_paths'] == 1 and row['progress'] == 33.33  # Pinned legacy reference version is still not an assignment.


def test_authoring_content_pages_keep_every_material_and_path_reachable(client):
    teacher, _ = account(client, 'content_page_owner', 'teacher')
    cid = course(teacher)
    with session() as db, db.begin():
        for i in range(101):
            db.add(Lesson(id=f'lesson-{i:03}', course_id=cid))
            db.add(LearningPath(id=f'path-{i:03}', course_id=cid))
        db.flush()
        for i in range(101):
            db.add(LessonVersion(id=f'lv-{i:03}', lesson_id=f'lesson-{i:03}', title=f'Material {i}', body_markdown='Text', body_html='<p>Text</p>'))
            db.add(PathVersion(id=f'pv-{i:03}', path_id=f'path-{i:03}', title=f'Path {i}', description='', languages=['c17']))
    first = teacher.get(f'/author/courses/{cid}/content').json()['lessons']
    last = teacher.get(f'/author/courses/{cid}/content?offset=100').json()['lessons']
    assert len(first) == 100 and [m['id'] for m in last] == ['lv-100']
    assert len(teacher.get(f'/author/courses/{cid}/paths').json()) == 100
    assert [p['id'] for p in teacher.get(f'/author/courses/{cid}/paths?offset=100').json()] == ['pv-100']


def test_dashboard_counts_all_accepted_exercises_and_respects_private_and_archive_access(client, monkeypatch):
    teacher, student, cid, path, problem, _ = setup_path(client, monkeypatch)
    e = enroll(student, path)
    read_all(student, e)
    stub_results(monkeypatch)
    original = student.post('/submissions', json=submission_body(e, problem)).json()
    run_attempt.run(original['attempt_id'])
    uid = student.get('/auth/me').json()['id']
    with session() as db, db.begin():
        for i in range(101):
            run = Submission(owner_id=uid, problem_version_id=problem['id'], language='c17', source='int main(){}',
                             mode='run', request_hash='test', created_at=utcnow() + timedelta(seconds=i+1))
            db.add(run)
            db.flush()
            db.add(Attempt(submission_id=run.id, provider='custom', snapshot={}, state='completed', verdict='EXECUTED'))
    assert all(s['mode'] == 'run' for s in student.get('/submissions').json())
    assert student.get('/my/stats').json()['accepted_exercises'] == 1
    outsider, _ = account(client, 'stats_other', 'student')
    assert outsider.get('/my/stats').json()['accepted_exercises'] == 0
    teacher.patch(f'/courses/{cid}/settings', json={'title': 'Private', 'is_public': False, 'edit_revision': 1})
    teacher.delete(f'/courses/{cid}/members/{uid}')
    assert student.get('/my/stats').json()['accepted_exercises'] == 0
    teacher.post(f'/courses/{cid}/archive')
    assert student.get('/my/stats').json()['accepted_exercises'] == 0


def test_report_query_count_is_bounded_for_class_and_path(client, monkeypatch):
    teacher, _, cid, path, _, payload = setup_path(client, monkeypatch)
    paths = [path]
    for i in range(4):
        p = teacher.post(f'/author/courses/{cid}/paths', json={**payload, 'title': f'Path {i}'}).json()
        teacher.post(f"/author/path-versions/{p['id']}/publish", json={'edit_revision': 1})
        paths.append(p)
    with session() as db, db.begin():
        for i in range(40):
            user = User(username=f'audit_load_{i:02}', password_hash='not-used-for-login', role='student')
            db.add(user)
            db.flush()
            db.add(CourseMember(course_id=cid, user_id=user.id))
            for p in paths:
                db.add(PathEnrollment(user_id=user.id, path_id=p['path_id'], path_version_id=p['id']))
    for url in (f'/author/courses/{cid}/progress', f"/author/paths/{path['path_id']}/progress"):
        statements = []
        def before(conn, cursor, statement, parameters, context, many):
            if statement.lstrip().upper().startswith('SELECT'):
                statements.append(statement)
        event.listen(engine(), 'before_cursor_execute', before)
        try:
            response = teacher.get(url)
        finally:
            event.remove(engine(), 'before_cursor_execute', before)
        assert response.status_code == 200
        rows = response.json() if isinstance(response.json(), list) else response.json()['participants']
        assert len(rows) == 41
        assert len(statements) <= 18, f'{len(statements)} SELECTs for {url}'
