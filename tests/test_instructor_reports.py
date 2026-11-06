from sqlalchemy import select

from app.db import session
from app.models import Attempt, AuditEvent, Completion, Course, LearningPath, PathEnrollment, Submission, User
from app.tasks import run_attempt
from tests.test_api_tasks import client
from tests.test_accounts_content import account
from tests.test_learning import setup_path, enroll, read_all, stub_results, submission_body


def test_class_progress_equal_path_weights_partial_and_unstarted(client, monkeypatch):
    teacher, student, cid, path, problem, payload = setup_path(client, monkeypatch)
    e = enroll(student, path)
    second = teacher.post(f'/author/courses/{cid}/paths', json={**payload, 'title': 'Second', 'steps': payload['steps'][:2]}).json()
    teacher.post(f"/author/path-versions/{second['id']}/publish", json={'edit_revision': 1})
    teacher.post(f'/author/courses/{cid}/paths', json={**payload, 'title': 'Draft excluded'})
    uid = student.get('/auth/me').json()['id']
    with session() as db, db.begin():
        db.get(User, uid).full_name = 'Peserta Bernama'
    student.post(f"/enrollments/{e['id']}/steps/{e['steps'][0]['id']}/complete")
    rows = teacher.get(f'/author/courses/{cid}/progress').json()
    assert len(rows) == 1
    assert rows[0]['full_name'] == 'Peserta Bernama'
    assert rows[0]['progress'] == 16.67  # (1/3 + 0)/2; avoid averaging rounded 33%.
    assert rows[0]['total_paths'] == 2 and rows[0]['started_paths'] == 1
    assert 'title' not in rows[0] and 'email' not in rows[0]
    read_all(student, e)
    stub_results(monkeypatch)
    r = student.post('/submissions', json=submission_body(e, problem)).json()
    run_attempt.run(r['attempt_id'])
    assert teacher.get(f'/author/courses/{cid}/progress').json()[0]['progress'] == 50
    e2 = enroll(student, second)
    student.post(f"/enrollments/{e2['id']}/steps/{e2['steps'][0]['id']}/complete")
    assert teacher.get(f'/author/courses/{cid}/progress').json()[0]['progress'] == 75
    read_all(student, e2)
    assert teacher.get(f'/author/courses/{cid}/progress').json()[0]['progress'] == 100
    teacher.post(f"/author/paths/{second['path_id']}/archive")
    row = teacher.get(f'/author/courses/{cid}/progress').json()[0]
    assert row['progress'] == 100 and row['total_paths'] == 1
    assert teacher.get(f'/author/courses/{cid}/progress?offset=100').json() == []


def test_reports_include_unstarted_members_and_keep_pinned_versions(client, monkeypatch):
    teacher, student, cid, path, _, _ = setup_path(client, monkeypatch)
    uid = student.get('/auth/me').json()['id']
    rows = teacher.get(f'/author/courses/{cid}/progress').json()
    assert len(rows) == 1 and rows[0]['progress'] == 0
    report = teacher.get(f"/author/paths/{path['path_id']}/progress").json()
    assert report['participants'][0]['enrollment'] is None
    detail_url = f"/author/paths/{path['path_id']}/participants/{uid}"
    assert teacher.get(detail_url).json()['submissions'] == []
    e = enroll(student, path)
    student.post(f"/enrollments/{e['id']}/steps/{e['steps'][0]['id']}/complete")
    revision = teacher.post(f"/author/paths/{path['path_id']}/versions").json()
    teacher.post(f"/author/path-versions/{revision['id']}/publish", json={'edit_revision': 1})
    detail = teacher.get(detail_url).json()
    assert detail['enrollment']['path_version_id'] == path['id']
    assert detail['enrollment']['completed_count'] == 1
    teacher.post(f'/courses/{cid}/archive')
    assert teacher.get(detail_url).status_code == 200
    assert client.get(detail_url).status_code == 200
    assert student.get(detail_url).status_code == 404


def test_work_history_is_scoped_to_student_and_path(client, monkeypatch):
    teacher, student, cid, path, problem, payload = setup_path(client, monkeypatch)
    e = enroll(student, path)
    read_all(student, e)
    stub_results(monkeypatch)
    original = student.post('/submissions', json=submission_body(e, problem)).json()
    run_attempt.run(original['attempt_id'])
    other_path = teacher.post(f'/author/courses/{cid}/paths', json=payload).json()
    teacher.post(f"/author/path-versions/{other_path['id']}/publish", json={'edit_revision': 1})
    e2 = enroll(student, other_path)
    read_all(student, e2)
    other = student.post('/submissions', json=submission_body(e2, problem)).json()
    uid = student.get('/auth/me').json()['id']
    url = f"/author/paths/{path['path_id']}/participants/{uid}"
    data = teacher.get(url).json()
    assert [r['id'] for r in data['submissions']] == [original['id']]
    assert data['submissions'][0]['step_title'] == 'Jumlah dua bilangan'
    assert 'source' not in data['submissions'][0]  # Source only requested on explicit review.
    assert teacher.get(url + '?offset=100').json()['submissions'] == []
    foreign, _ = account(client, 'foreign_report_teacher', 'teacher')
    outsider, outsider_user = account(client, 'foreign_report_student', 'student')
    for viewer in (student, outsider, foreign):
        assert viewer.get(url).status_code == 404
        assert viewer.get(f"/author/paths/{path['path_id']}/progress").status_code == 404
        assert viewer.get(f'/author/courses/{cid}/progress').status_code == 404
    assert teacher.get(f"/author/paths/{path['path_id']}/participants/{outsider_user['id']}").status_code == 404


def test_teacher_replay_uses_exact_source_without_altering_student_results(client, monkeypatch):
    teacher, student, cid, path, problem, _ = setup_path(client, monkeypatch)
    e = enroll(student, path)
    read_all(student, e)
    stub_results(monkeypatch)
    original = student.post('/submissions', json=submission_body(e, problem)).json()
    run_attempt.run(original['attempt_id'])
    before = student.get(f"/enrollments/{e['id']}").json()
    # The learner's original version remains executable after a new problem revision publishes.
    revision = teacher.post(f"/author/problems/{problem['problem_id']}/versions").json()
    with session() as db, db.begin():
        from app.models import Problem, ProblemVersion
        db.get(ProblemVersion, revision['id']).status = 'published'
        db.get(Problem, problem['problem_id']).published_version_id = revision['id']
    url = f"/author/submissions/{original['id']}/run"
    response = teacher.post(url, json={'input': '2 3\n'})
    assert response.status_code == 202, response.text
    replay = response.json()
    run_attempt.run(replay['attempt_id'])
    with session() as db:
        r = db.get(Submission, replay['id'])
        source = db.get(Submission, original['id'])
        assert r.owner_id != source.owner_id and r.source == source.source and r.language == source.language
        assert r.mode == 'run' and r.enrollment_id is None and r.path_step_id is None
        assert r.custom_input == '2 3\n'
        assert db.get(Attempt, original['attempt_id']).verdict == 'ACCEPTED'
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == 'submission.instructor_run')).object_id == original['id']
    after = student.get(f"/enrollments/{e['id']}").json()
    assert (after['progress'], after['score'], after['completed_at']) == (before['progress'], before['score'], before['completed_at'])
    assert teacher.post(url, json={'input': '', 'source': 'tamper'}).status_code == 422
    assert student.post(url, json={'input': ''}).status_code == 404
    foreign, _ = account(client, 'foreign_replay_teacher', 'teacher')
    assert foreign.post(url, json={'input': ''}).status_code == 404
    teacher.post(f'/courses/{cid}/archive')
    assert teacher.post(url, json={'input': ''}).status_code == 409
