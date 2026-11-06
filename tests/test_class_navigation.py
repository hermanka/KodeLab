from sqlalchemy import select

from app.db import session
from app.models import Course
from tests.test_api_tasks import client
from tests.test_accounts_content import account, course
from tests.test_learning import setup_path, enroll


def test_class_page_scopes_paths_and_only_exposes_own_enrollment(client, monkeypatch):
    teacher, student, cid, path, _, _ = setup_path(client, monkeypatch)
    e = enroll(student, path)
    other, _ = account(client, 'class_other_student', 'student')
    foreign = course(teacher, public=True)
    response = student.get(f'/courses/{cid}/learning')
    assert response.status_code == 200
    page = response.json()
    assert page['course']['id'] == cid and not page['course']['can_manage']
    assert [p['id'] for p in page['paths']] == [path['path_id']]
    assert [r['id'] for r in page['enrollments']] == [e['id']]
    assert other.get(f'/courses/{cid}/learning').json()['enrollments'] == []
    assert teacher.get(f'/courses/{cid}/learning').json()['course']['can_manage']
    assert student.get(f'/courses/{foreign}/learning').json()['paths'] == []
    assert student.get('/paths', params={'course_id': foreign}).json() == []


def test_private_class_page_denies_direct_access_and_revocation(client, monkeypatch):
    teacher, student, cid, path, _, _ = setup_path(client, monkeypatch)
    e = enroll(student, path)
    outsider, _ = account(client, 'class_outsider', 'student')
    with session() as db, db.begin():
        db.get(Course, cid).is_public = False
    assert outsider.get(f'/courses/{cid}/learning').status_code == 404
    assert outsider.get('/paths', params={'course_id': cid}).status_code == 404
    assert student.get(f'/courses/{cid}/learning').status_code == 200
    user_id = student.get('/auth/me').json()['id']
    teacher.delete(f'/courses/{cid}/members/{user_id}')
    assert student.get(f'/courses/{cid}/learning').status_code == 404
    assert student.get(f"/enrollments/{e['id']}").status_code == 404


def test_class_page_keeps_pinned_and_archived_path_progress(client, monkeypatch):
    teacher, student, cid, path, _, _ = setup_path(client, monkeypatch)
    e = enroll(student, path)
    first = e['steps'][0]['id']
    student.post(f"/enrollments/{e['id']}/steps/{first}/complete")
    revision = teacher.post(f"/author/paths/{path['path_id']}/versions").json()
    teacher.post(f"/author/path-versions/{revision['id']}/publish", json={'edit_revision': 1})
    page = student.get(f'/courses/{cid}/learning').json()
    assert page['paths'][0]['revision'] == 2
    assert page['enrollments'][0]['path_version_id'] == path['id']
    assert page['enrollments'][0]['completed_count'] == 1
    teacher.post(f"/author/paths/{path['path_id']}/archive")
    page = student.get(f'/courses/{cid}/learning').json()
    assert page['paths'] == [] and page['enrollments'][0]['id'] == e['id']
    teacher.post(f'/courses/{cid}/archive')
    assert student.get(f'/courses/{cid}/learning').status_code == 404
    assert teacher.get(f'/courses/{cid}/learning').json()['course']['archived']
    teacher.post(f'/courses/{cid}/restore')
    assert student.get(f'/courses/{cid}/learning').json()['enrollments'][0]['completed_count'] == 1
