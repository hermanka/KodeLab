from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import session
from app.main import app
from app.models import Completion, Course, PathEnrollment, PathStep, User, utcnow
from app.tasks import run_attempt
from tests.test_api_tasks import client
from tests.test_accounts_content import account, course, draft, fake_judge, validate
from tests.test_learning import setup_path, enroll, stub_results


def finish(enrollment, seconds, optional=False):
    with session() as db, db.begin():
        e = db.get(PathEnrollment, enrollment['id'])
        e.created_at = utcnow() - timedelta(days=2)
        steps = list(db.scalars(select(PathStep).where(PathStep.path_version_id == e.path_version_id)))
        for step in steps:
            if step.required or optional:
                db.add(Completion(enrollment_id=e.id, step_id=step.id,
                                  created_at=e.created_at + timedelta(seconds=seconds if step.required else seconds + 100)))


def test_scores_tie_by_final_duration_and_shared_rank(client, monkeypatch):
    teacher, student, cid, path, _, payload = setup_path(client, monkeypatch)
    other, _ = account(client, 'fast_student', 'student')
    third, _ = account(client, 'same_fast_student', 'student')
    slow, fast, same = enroll(student, path), enroll(other, path), enroll(third, path)
    finish(slow, 120)
    finish(fast, 60)
    finish(same, 60)
    url = f"/courses/{path['course_id']}/leaderboard"
    rows = student.get(url).json()['rows']
    assert [r['rank'] for r in rows] == [1, 1, 3]
    assert [r['completion_seconds'] for r in rows] == [60, 60, 120]
    assert all(r['score'] == 100 for r in rows)
    for viewer in (client, teacher, student):
        assert viewer.get(url).status_code == 200
        board = viewer.get('/leaderboards').json()['rows']
        assert [r['rank'] for r in board] == [1, 1, 3]
        assert all(r['score'] == 100 and r['completed_paths'] == 1 for r in board)
    assert TestClient(app).get('/leaderboards').status_code == 401
    assert TestClient(app).get(url).status_code == 401
    second = teacher.post(f'/author/courses/{cid}/paths', json={**payload, 'title': 'Jalur kedua'}).json()
    assert teacher.post(f"/author/path-versions/{second['id']}/publish", json={'edit_revision': 1}).status_code == 200
    another = enroll(student, second)
    finish(another, 600)
    global_rows = student.get('/leaderboards').json()['rows']
    # Total score precedes speed: two completed paths beat one faster path.
    assert global_rows[0]['username'] == 'student_path'
    assert global_rows[0]['score'] == 200 and global_rows[0]['completion_seconds'] == 720
    assert global_rows[0]['completed_paths'] == 2


def test_elapsed_freezes_and_optional_completion_does_not_change_it(client, monkeypatch):
    _, student, _, path, _, _ = setup_path(client, monkeypatch, optional=True)
    e = enroll(student, path)
    assert e['score'] == 0 and e['completion_seconds'] is None
    finish(e, 90, optional=True)
    first = student.get(f"/enrollments/{e['id']}").json()
    assert first['complete'] and first['elapsed_seconds'] == 90
    assert first['completion_seconds'] == 90 and first['score'] == 100
    # A repeat request cannot replace the original completion timestamp.
    reading = next(s for s in first['steps'] if s['kind'] == 'reading' and s['required'])
    again = student.post(f"/enrollments/{e['id']}/steps/{reading['id']}/complete").json()
    assert again['completed_at'] == first['completed_at']
    assert again['elapsed_seconds'] == 90


def test_partial_score_does_not_gain_final_time_or_repeat_points(client, monkeypatch):
    teacher, student, _, path, _, _ = setup_path(client, monkeypatch)
    e = enroll(student, path)
    # An exercise may be accepted before all reading steps in a nonsequential path.
    with session() as db, db.begin():
        db.add(Completion(enrollment_id=e['id'], step_id=e['steps'][-1]['id']))
    partial = student.get(f"/enrollments/{e['id']}").json()
    assert partial['score'] == 100 and not partial['complete'] and partial['completion_seconds'] is None
    total = student.get('/leaderboards').json()['rows'][0]
    assert total['score'] == 100 and total['completion_seconds'] is None
    for _ in range(2):
        student.post(f"/enrollments/{e['id']}/steps/{e['steps'][0]['id']}/complete")
    assert student.get('/leaderboards').json()['rows'][0]['score'] == 100


def test_private_class_scope_and_revoked_or_inactive_participants(client, monkeypatch):
    teacher, student, cid, path, _, _ = setup_path(client, monkeypatch)
    outsider, _ = account(client, 'outside_board', 'student')
    e = enroll(student, path)
    finish(e, 50)
    with session() as db, db.begin():
        db.get(Course, cid).is_public = False
    url = f"/courses/{path['course_id']}/leaderboard"
    assert outsider.get(url).status_code == 404
    assert outsider.get('/leaderboards').json()['rows'] == []
    assert len(teacher.get('/leaderboards').json()['rows']) == 1
    with session() as db, db.begin():
        db.scalar(select(User).where(User.username == 'student_path')).is_active = False
    assert teacher.get(url).json()['rows'] == []
    with session() as db, db.begin():
        db.scalar(select(User).where(User.username == 'student_path')).is_active = True
    user_id = student.get('/auth/me').json()['id']
    assert teacher.delete(f'/courses/{cid}/members/{user_id}').status_code == 200
    assert teacher.get(url).json()['rows'] == []


def test_revisions_keep_class_and_global_score_without_duplicate_points(client, monkeypatch):
    teacher, student, _, path, _, _ = setup_path(client, monkeypatch)
    e = enroll(student, path)
    finish(e, 75)
    revised = teacher.post(f"/author/paths/{path['path_id']}/versions").json()
    assert teacher.post(f"/author/path-versions/{revised['id']}/publish", json={'edit_revision': 1}).status_code == 200
    url = f"/courses/{path['course_id']}/leaderboard"
    rows = student.get(url).json()['rows']
    assert len(rows) == 1 and rows[0]['score'] == 100
    assert rows[0]['completed_paths'] == 1
    assert student.get(f"/enrollments/{e['id']}").json()['path_version_id'] == path['id']
    assert student.get(f"/paths/{path['path_id']}/leaderboard").status_code == 404
    assert student.get('/leaderboards').json()['rows'][0]['score'] == 100


def test_standalone_exercises_are_unavailable_to_students(client):
    student, _ = account(client, 'no_standalone', 'student')
    assert student.get('/problems').json() == []
    assert student.get('/problems/sum-v1').status_code == 403
    for endpoint in ('/runs', '/submissions'):
        assert student.post(endpoint, json={'source': 'int main(){}', 'language': 'c17'}).status_code == 403


def test_score_uses_accepted_required_exercises_not_runs_or_wrong_answers(client, monkeypatch):
    teacher, student, cid, _, problem, _ = setup_path(client, monkeypatch)
    path = teacher.post(f'/author/courses/{cid}/paths', json={
        'title': 'Dua latihan wajib', 'sequential': False,
        'steps': [{'key': key, 'title': key, 'kind': 'exercise', 'problem_version_id': problem['id']}
                  for key in ('first', 'second')]}).json()
    assert teacher.post(f"/author/path-versions/{path['id']}/publish", json={'edit_revision': 1}).status_code == 200
    e = enroll(student, path)
    body = {'enrollment_id': e['id'], 'problem_version_id': problem['id'],
            'language': 'c17', 'source': 'int main(){}'}
    stub_results(monkeypatch)
    row = student.post('/submissions', json={**body, 'path_step_id': e['steps'][0]['id']}).json()
    run_attempt.run(row['attempt_id'])
    summary = student.get(f"/enrollments/{e['id']}").json()
    assert summary['score'] == 50 and summary['completion_seconds'] is None
    for endpoint, accepted in (('/runs', True), ('/submissions', False)):
        stub_results(monkeypatch, accepted)
        row = student.post(endpoint, json={**body, 'path_step_id': e['steps'][1]['id']}).json()
        run_attempt.run(row['attempt_id'])
        assert student.get(f"/enrollments/{e['id']}").json()['score'] == 50
    stub_results(monkeypatch)
    row = student.post('/submissions', json={**body, 'path_step_id': e['steps'][1]['id']}).json()
    run_attempt.run(row['attempt_id'])
    result = student.get(f"/courses/{path['course_id']}/leaderboard").json()['rows'][0]
    assert result['score'] == 100 and result['completion_seconds'] is not None


def test_class_score_isolated_from_other_classes_and_aggregates_paths(client, monkeypatch):
    teacher, student, cid, path, _, payload = setup_path(client, monkeypatch)
    slow = enroll(student, path)
    finish(slow, 120)
    fast_student, _ = account(client, 'class_fast', 'student')
    fast = enroll(fast_student, path)
    finish(fast, 60)
    url = f'/courses/{cid}/leaderboard'
    assert [r['username'] for r in student.get(url).json()['rows']] == ['class_fast', 'student_path']
    second = teacher.post(f'/author/courses/{cid}/paths', json={**payload, 'title': 'Jalur kedua'}).json()
    teacher.post(f"/author/path-versions/{second['id']}/publish", json={'edit_revision': 1})
    finish(enroll(student, second), 180)
    rows = student.get(url).json()['rows']
    assert rows[0]['score'] == 200 and rows[0]['completion_seconds'] == 300
    assert rows[0]['completed_paths'] == 2
    foreign_course = course(teacher, public=True)
    problem = draft(teacher, foreign_course)
    fake_judge(monkeypatch)
    validate(teacher, problem)
    teacher.post(f"/author/problem-versions/{problem['id']}/publish", json={'edit_revision': 1})
    foreign_path = teacher.post(f'/author/courses/{foreign_course}/paths', json={
        'title': 'Jalur kelas lain', 'steps': [{'key': 'sum', 'title': 'Sum', 'kind': 'exercise', 'problem_version_id': problem['id']}]}).json()
    teacher.post(f"/author/path-versions/{foreign_path['id']}/publish", json={'edit_revision': 1})
    finish(enroll(student, foreign_path), 10)
    assert student.get(url).json()['rows'] == rows
    assert student.get('/leaderboards').json()['rows'][0]['score'] == 300
    assert student.get(f'/courses/{foreign_course}/leaderboard').json()['rows'][0]['score'] == 100
    teacher.post(f'/courses/{cid}/archive')
    assert student.get(url).status_code == 404
    assert teacher.get(url).json()['rows'] == rows
    assert student.get('/leaderboards').json()['rows'][0]['score'] == 100
    teacher.post(f'/courses/{cid}/restore')
    teacher.post(f"/author/paths/{second['path_id']}/archive")
    assert student.get(url).json()['rows'][0]['score'] == 100
