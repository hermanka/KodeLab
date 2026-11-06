import pytest
from sqlalchemy import event, func, select

from app.db import engine, session
from app.models import (Attempt, Completion, Course, CourseMember, LearningPath, Lesson,
                        LessonVersion, PathEnrollment, PathStep, PathVersion, Problem,
                        ProblemVersion, ReferenceSolution, Submission, TestCase as CaseModel,
                        User, ValidationJob)
from app.tasks import run_attempt, run_validation
from tests.test_api_tasks import client
from tests.test_accounts_content import account, course
from tests.test_learning import setup_path, enroll, read_all, stub_results, submission_body


@pytest.fixture(autouse=True)
def enforce_foreign_keys(client):
    def enable(connection, record, proxy):
        connection.execute('PRAGMA foreign_keys=ON')
    event.listen(engine(), 'checkout', enable)
    yield
    event.remove(engine(), 'checkout', enable)


def test_archive_is_read_only_and_restore_preserves_progress(client, monkeypatch):
    teacher, student, cid, path, problem, _ = setup_path(client, monkeypatch)
    e = enroll(student, path)
    first = e['steps'][0]['id']
    assert student.post(f"/enrollments/{e['id']}/steps/{first}/complete").status_code == 200
    stranger, _ = account(client, 'archive_stranger', 'student')
    assigned, assigned_user = account(client, 'archive_assigned', 'teacher')
    teacher.post(f'/courses/{cid}/members', json={'user_id': assigned_user['id'], 'role': 'teacher'})
    assert student.post(f'/courses/{cid}/archive').status_code == 404
    assert assigned.post(f'/courses/{cid}/archive').status_code == 404
    assert teacher.post(f'/courses/{cid}/archive').status_code == 200
    assert teacher.post(f'/courses/{cid}/archive').status_code == 200
    assert cid not in [p['course_id'] for p in student.get('/paths').json()]
    assert stranger.post(f"/paths/{path['path_id']}/enroll").status_code == 404
    assert student.get(f"/enrollments/{e['id']}").status_code == 404
    assert student.get(f"/enrollments/{e['id']}/steps/{first}").status_code == 404
    assert student.post(f"/enrollments/{e['id']}/steps/{first}/complete").status_code == 404
    assert teacher.post(f'/author/courses/{cid}/lessons', json={'title': 'No', 'body_markdown': 'No'}).status_code == 409
    assert teacher.post(f"/author/problems/{problem['problem_id']}/versions").status_code == 409
    assert student.get('/leaderboards').json()['rows'] == []
    assert student.get(f'/courses/{cid}/leaderboard').status_code == 404
    assert teacher.get(f'/courses/{cid}/leaderboard').status_code == 200
    assert teacher.get(f'/author/courses/{cid}/content').status_code == 200
    assert client.post(f'/courses/{cid}/restore').status_code == 200
    assert student.get(f"/enrollments/{e['id']}").json()['completed_count'] == 1
    assert student.post(f"/enrollments/{e['id']}/steps/{e['steps'][1]['id']}/complete").status_code == 200


def populated_class(client, monkeypatch):
    teacher, student, cid, path, problem, _ = setup_path(client, monkeypatch)
    e = enroll(student, path)
    read_all(student, e)
    stub_results(monkeypatch)
    body = submission_body(e, problem)
    accepted = student.post('/submissions', json=body).json()
    run_attempt.run(accepted['attempt_id'])
    queued = student.post('/runs', json=body).json()
    # Include old content versions, private reference solutions and pending validation.
    revised = teacher.post(f"/author/problems/{problem['problem_id']}/versions").json()
    validation = teacher.post(f"/author/problem-versions/{revised['id']}/validate", json={'edit_revision': 1}).json()
    return teacher, student, cid, e, queued, validation


def counts():
    models = (Course, CourseMember, Lesson, LessonVersion, Problem, ProblemVersion, ReferenceSolution,
              CaseModel, ValidationJob, LearningPath, PathVersion, PathStep, PathEnrollment,
              Completion, Submission, Attempt, User)
    with session() as db:
        return {m.__tablename__: db.scalar(select(func.count()).select_from(m)) for m in models}


def test_delete_removes_all_academic_data_but_not_other_classes_or_accounts(client, monkeypatch):
    teacher, student, cid, e, queued, validation = populated_class(client, monkeypatch)
    other = course(client, public=True)
    outsider, _ = account(client, 'delete_outsider', 'teacher')
    title = next(c['title'] for c in teacher.get('/courses').json() if c['id'] == cid)
    body = {'confirmation_title': title}
    assert outsider.request('DELETE', f'/courses/{cid}', json=body).status_code == 404
    assert student.request('DELETE', f'/courses/{cid}', json=body).status_code == 404
    assert teacher.request('DELETE', f'/courses/{cid}', json={'confirmation_title': 'wrong'}).status_code == 422
    before = counts()
    assert teacher.request('DELETE', f'/courses/{cid}', json=body).status_code == 200
    after = counts()
    assert after['users'] == before['users']
    assert after['courses'] == 1
    assert all(count == 0 for table, count in after.items() if table not in ('users', 'courses', 'problem_versions', 'test_cases'))
    # Seed problem is unrelated and must survive.
    assert after['problem_versions'] == 1 and after['test_cases'] > 0
    with session() as db:
        assert db.get(Course, other)
        assert not db.get(Course, cid)
    assert student.get(f"/enrollments/{e['id']}").status_code == 404
    assert student.get(f"/submissions/{queued['id']}").status_code == 404
    assert student.get('/submissions').json() == []
    assert student.get('/leaderboards').json()['rows'] == []
    # Already-published Celery messages cannot resurrect academic records.
    run_attempt.run(queued['attempt_id'])
    run_validation.run(validation['id'])
    assert counts() == after
    assert teacher.request('DELETE', f'/courses/{cid}', json=body).status_code == 404


@pytest.mark.parametrize('running_model', [Attempt, ValidationJob])
def test_running_jobs_block_deletion_without_partial_changes(client, monkeypatch, running_model):
    teacher, _, cid, _, queued, validation = populated_class(client, monkeypatch)
    with session() as db, db.begin():
        db.get(running_model, queued['attempt_id'] if running_model == Attempt else validation['id']).state = 'running'
    before = counts()
    title = next(c['title'] for c in teacher.get('/courses').json() if c['id'] == cid)
    assert teacher.request('DELETE', f'/courses/{cid}', json={'confirmation_title': title}).status_code == 409
    assert counts() == before


def test_deletion_rolls_back_all_tables_on_failure(client, monkeypatch):
    teacher, _, cid, _, _, _ = populated_class(client, monkeypatch)
    title = next(c['title'] for c in teacher.get('/courses').json() if c['id'] == cid)
    before = counts()
    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith('DELETE FROM problem_versions'):
            raise RuntimeError('injected deletion failure')
    event.listen(engine(), 'before_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='injected deletion failure'):
            teacher.request('DELETE', f'/courses/{cid}', json={'confirmation_title': title})
    finally:
        event.remove(engine(), 'before_cursor_execute', fail)
    assert counts() == before


def test_status_filter_is_applied_before_limit_and_preserves_permissions(client):
    teacher, teacher_user = account(client, 'status_teacher', 'teacher')
    student, student_user = account(client, 'status_student', 'student')
    with session() as db, db.begin():
        for i in range(101):
            db.add(Course(id=f'archive-{i:03}', owner_id=teacher_user['id'], title=f'Arsip {i}', archived=True))
        db.add(Course(id='z-active', owner_id=teacher_user['id'], title='Kelas aktif', is_public=True))
        db.add(CourseMember(course_id='archive-000', user_id=student_user['id'], role='student'))
    active = teacher.get('/courses', params={'status': 'active'}).json()
    assert [c['id'] for c in active] == ['z-active']
    archived = teacher.get('/courses', params={'status': 'archived'}).json()
    assert len(archived) == 100 and all(c['archived'] for c in archived)
    next_page = teacher.get('/courses', params={'status': 'archived', 'offset': 100}).json()
    assert len(next_page) == 1 and next_page[0]['archived']
    visible = student.get('/courses', params={'status': 'archived'}).json()
    assert visible == []
    assert student.get('/courses', params={'status': 'active'}).json()[0]['id'] == 'z-active'
    assert teacher.get('/courses', params={'status': 'unknown'}).status_code == 422
