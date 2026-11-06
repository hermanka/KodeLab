from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import COOKIE, digest, hasher
from app.contracts import CaseResult, JudgeResult
from app.db import session
from app.main import app
from app.models import AuditEvent, AuthSession, ProblemVersion, ReferenceSolution, User, ValidationJob, utcnow
from app.providers import CustomProvider, ProviderUnavailable
from tests.test_api_tasks import client  # Shared isolated database fixture.

PASSWORD = "test-password-long-enough"


def account(admin, username, role):
    response = admin.post("/admin/users", json={"username": username, "password": PASSWORD, "role": role})
    assert response.status_code == 201, response.text
    user = response.json()
    client = TestClient(app)
    login = client.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert login.status_code == 200
    client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
    return client, user


def course(teacher, public=False):
    response = teacher.post("/courses", json={"title": "Dasar C/C++", "is_public": public})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def package():
    return {"title": "Jumlah", "statement": "Baca a dan b, cetak jumlahnya.", "languages": ["c17", "cpp17"],
            "cases": [{"input": "2 3\n", "expected": "5\n", "public": True},
                      {"input": "-7 -8\n", "expected": "-15\n", "public": False}],
            "reference_solutions": {"c17": "int main(){return 0;}", "cpp17": "int main(){return 0;}"}}


def draft(teacher, course_id):
    response = teacher.post(f"/author/courses/{course_id}/problems", json=package())
    assert response.status_code == 201, response.text
    return response.json()


def fake_judge(monkeypatch, verdict="ACCEPTED"):
    requests = []

    def submit(self, request, key):
        requests.append(request)
        self._result = JudgeResult(verdict=verdict, cases=[CaseResult(id=c.id, verdict=verdict) for c in request.cases])
        self._reference = key
        return key

    monkeypatch.setattr(CustomProvider, "submit", submit)
    return requests


def validate(teacher, version):
    from app.tasks import run_validation
    response = teacher.post(f"/author/problem-versions/{version['id']}/validate", json={"edit_revision": version["edit_revision"]})
    assert response.status_code == 202, response.text
    run_validation.run(response.json()["id"])
    return teacher.get(f"/author/validations/{response.json()['id']}").json()


def test_registration_cannot_grant_roles_and_errors_do_not_echo_password(client):
    anonymous = TestClient(app)
    assert anonymous.post("/auth/register", json={"username": "student_new", "password": PASSWORD, "role": "admin"}).status_code == 422
    response = anonymous.post("/auth/register", json={"username": "student_new", "password": PASSWORD, "full_name": "Student New", "email": "student_new@example.test"})
    assert response.status_code == 201 and response.json()["role"] == "student"
    response = anonymous.post("/auth/register", json={"username": "student_bad", "password": "short-secret"})
    assert response.status_code == 422 and "short-secret" not in response.text
    with session() as db:
        row = db.scalar(select(User).where(User.username == "student_new"))
        assert row.password_hash.startswith("$argon2id$") and row.password_hash != PASSWORD
        assert hasher.verify(row.password_hash, PASSWORD)


def test_bootstrap_validation_does_not_echo_secret(monkeypatch):
    import traceback
    from app.bootstrap import main
    secret = "private-short"
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", secret)
    with pytest.raises(RuntimeError) as caught:
        main()
    rendered = "".join(traceback.format_exception(caught.type, caught.value, caught.tb))
    assert secret not in rendered and "Invalid bootstrap" in rendered


def test_cookie_csrf_origin_logout_and_revocation(client):
    browser = TestClient(app)
    response = browser.post("/auth/login", json={"username": "test_admin", "password": PASSWORD})
    token, csrf = response.json()["access_token"], response.json()["csrf_token"]
    assert "httponly" in response.headers.get_list("set-cookie")[0].lower()
    assert browser.get("/auth/me").status_code == 200
    assert browser.post("/courses", json={"title": "Blocked"}).status_code == 403
    assert browser.post("/courses", json={"title": "Blocked"}, headers={"X-CSRF-Token": csrf, "Origin": "https://evil.test"}).status_code == 403
    assert browser.post("/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert browser.get("/auth/me", headers={"Authorization": "Bearer " + token}).status_code == 401
    assert browser.get("/auth/me", headers={"X-API-Key": "old-shared-token"}).status_code == 401


def test_idle_session_expiry_and_permission_changes(client):
    student, user = account(client, "student_expire", "student")
    token = student.headers["Authorization"].split()[1]
    with session() as db, db.begin():
        db.get(AuthSession, digest(token)).last_seen = utcnow() - timedelta(minutes=31)
    assert student.get("/auth/me").status_code == 401
    teacher, user = account(client, "teacher_disable", "teacher")
    assert client.patch(f"/admin/users/{user['id']}", json={"is_active": False}).status_code == 200
    assert teacher.get("/auth/me").status_code == 401
    admin_id = client.get("/auth/me").json()["id"]
    assert client.patch(f"/admin/users/{admin_id}", json={"role": "student"}).status_code == 409


def test_login_rate_limit_persists_failed_attempts(client):
    anonymous = TestClient(app)
    for _ in range(10):
        assert anonymous.post("/auth/login", json={"username": "unknown_user", "password": PASSWORD}).status_code == 401
    assert anonymous.post("/auth/login", json={"username": "unknown_user", "password": PASSWORD}).status_code == 429


def exercise_context(teacher, student, monkeypatch, cid=None, version=None):
    cid = cid or course(teacher, public=True)
    if version is None:
        version = draft(teacher, cid)
        fake_judge(monkeypatch)
        validate(teacher, version)
        assert teacher.post(f"/author/problem-versions/{version['id']}/publish", json={"edit_revision": 1}).status_code == 200
    path = teacher.post(f'/author/courses/{cid}/paths', json={
        'title': 'Latihan melalui jalur', 'steps': [{'key': 'exercise', 'title': 'Latihan',
        'kind': 'exercise', 'problem_version_id': version['id']}]}).json()
    assert teacher.post(f"/author/path-versions/{path['id']}/publish", json={'edit_revision': 1}).status_code == 200
    e = student.post(f"/paths/{path['path_id']}/enroll").json()
    return {'problem_version_id': version['id'], 'enrollment_id': e['id'], 'path_step_id': e['steps'][0]['id']}


def test_ownership_and_idempotency_are_scoped_to_account(client, monkeypatch):
    one, _ = account(client, "student_one", "student")
    two, _ = account(client, "student_two", "student")
    key, body = str(uuid4()), {"language": "c17", "source": "int main(){}", **exercise_context(client, one, monkeypatch)}
    path = one.get(f"/enrollments/{body['enrollment_id']}").json()
    e = two.post(f"/paths/{path['path_id']}/enroll").json()
    first = one.post("/submissions", json=body, headers={"Idempotency-Key": key}).json()
    second = two.post("/submissions", json={**body, 'enrollment_id': e['id']}, headers={"Idempotency-Key": key}).json()
    assert first["id"] != second["id"]
    assert two.get(f"/submissions/{first['id']}").status_code == 404
    assert len(one.get("/submissions").json()) == 1
    assert one.post("/submissions", json={**body, "provider": "custom"}).status_code == 403
    assert one.post("/courses", json={"title": "No"}).status_code == 403
    assert one.post("/admin/users", json={"username": "extra", "password": PASSWORD}).status_code == 403
    assert client.get(f"/submissions/{first['id']}").status_code == 200


def test_material_sanitization_publication_revision_and_archive(client):
    teacher, _ = account(client, "teacher_material", "teacher")
    stranger, _ = account(client, "teacher_other", "teacher")
    student, user = account(client, "student_material", "student")
    cid = course(teacher)
    assert teacher.post(f"/courses/{cid}/members", json={"user_id": user["id"]}).status_code == 201
    data = {"title": "Input output", "body_markdown": '# Hi\n<script>alert(1)</script>\n[x](javascript:alert(2))\n```c\nint main(){}\n```'}
    response = teacher.post(f"/author/courses/{cid}/lessons", json=data)
    assert response.status_code == 201, response.text
    version = response.json()
    assert "<script>" not in version["body_html"] and 'href="javascript:' not in version["body_html"]
    assert student.get(f"/courses/{cid}/lessons").json() == []
    assert stranger.get(f"/author/lesson-versions/{version['id']}").status_code == 404
    assert student.get(f"/author/lesson-versions/{version['id']}").status_code == 404
    assert teacher.put(f"/author/lesson-versions/{version['id']}", json={**data, "edit_revision": 7}).status_code == 409
    assert teacher.post(f"/author/lesson-versions/{version['id']}/publish", json={"edit_revision": 1}).status_code == 200
    assert len(student.get(f"/courses/{cid}/lessons").json()) == 1
    assert teacher.put(f"/author/lesson-versions/{version['id']}", json={**data, "edit_revision": 1}).status_code == 409
    revision = teacher.post(f"/author/lessons/{version['lesson_id']}/versions").json()
    assert revision["revision"] == 2 and revision["status"] == "draft"
    assert student.get(f"/courses/{cid}/lessons").json()[0]["id"] == version["id"]
    assert teacher.post(f"/author/lessons/{version['lesson_id']}/archive").status_code == 200
    assert student.get(f"/courses/{cid}/lessons").json() == []


def test_problem_publication_requires_validated_current_keys(client, monkeypatch):
    teacher, _ = account(client, "teacher_problem", "teacher")
    student, user = account(client, "student_problem", "student")
    cid = course(teacher)
    teacher.post(f"/courses/{cid}/members", json={"user_id": user["id"]})
    version = draft(teacher, cid)
    url = f"/author/problem-versions/{version['id']}"
    assert student.get(f"/problems/{version['id']}").status_code == 404
    assert teacher.post(url + "/publish", json={"edit_revision": 1}).status_code == 409
    requests = fake_judge(monkeypatch)
    result = validate(teacher, version)
    assert result["valid"] and {r.language for r in requests} == {"c17", "cpp17"}
    assert teacher.post(url + "/publish", json={"edit_revision": 1}).status_code == 200
    public = teacher.get(f"/problems/{version['id']}").json()
    assert len(public["samples"]) == 1 and "reference_solutions" not in public and "cases" not in public
    assert student.get(url).status_code == 404
    assert student.get(f"/author/validations/{result['id']}").status_code == 404
    context = exercise_context(teacher, student, monkeypatch, cid, version)
    submitted = student.post("/submissions", json={**context, "language": "c17", "source": "int main(){}"})
    assert submitted.status_code == 202
    assert teacher.get(f"/submissions/{submitted.json()['id']}").status_code == 200
    assert teacher.get(f"/submissions?course_id={cid}").json()[0]["id"] == submitted.json()["id"]
    assert student.get(f"/submissions?course_id={cid}").status_code == 404
    assert teacher.get(f"/courses/{cid}/members").json()[0]["id"] == user["id"]
    assert student.get(f"/courses/{cid}/members").status_code == 404
    assert teacher.put(url, json={**package(), "edit_revision": 1}).status_code == 409
    revised = teacher.post(f"/author/problems/{version['problem_id']}/versions").json()
    assert revised["revision"] == 2 and revised["validation_job_id"] is None
    revised_url = f"/author/problem-versions/{revised['id']}"
    validate(teacher, revised)
    update = teacher.put(revised_url, json={**package(), "title": "Revised", "edit_revision": 1})
    assert update.status_code == 200 and update.json()["edit_revision"] == 2
    assert teacher.post(revised_url + "/publish", json={"edit_revision": 2}).status_code == 409
    with session() as db:
        assert db.get(ProblemVersion, version["id"]).status == "published"
        assert db.get(ReferenceSolution, (version["id"], "c17")).source == package()["reference_solutions"]["c17"]


def test_failed_reference_and_infrastructure_errors_do_not_allow_publication(client, monkeypatch):
    from app.tasks import run_validation
    teacher, _ = account(client, "teacher_bad_key", "teacher")
    version = draft(teacher, course(teacher))
    fake_judge(monkeypatch, "WRONG_ANSWER")
    result = validate(teacher, version)
    assert result["state"] == "completed" and result["valid"] is False
    url = f"/author/problem-versions/{version['id']}"
    assert teacher.post(url + "/publish", json={"edit_revision": 1}).status_code == 409
    response = teacher.post(url + "/validate", json={"edit_revision": 1})
    assert response.status_code == 202
    job_id = response.json()["id"]

    def unavailable(*args, **kwargs):
        raise ProviderUnavailable("offline")

    monkeypatch.setattr(CustomProvider, "submit", unavailable)
    for state in ("retry_pending", "retry_pending", "system_error"):
        run_validation.run(job_id)
        with session() as db:
            job = db.get(ValidationJob, job_id)
            assert job.state == state and job.valid is None
    assert teacher.get(url).json()["status"] == "draft"


def test_course_access_revocation_and_public_enrollment(client, monkeypatch):
    teacher, _ = account(client, "teacher_scope", "teacher")
    other, _ = account(client, "teacher_scope_other", "teacher")
    student, user = account(client, "student_scope", "student")
    cid = course(teacher, public=True)
    version = draft(teacher, cid)
    fake_judge(monkeypatch)
    validate(teacher, version)
    teacher.post(f"/author/problem-versions/{version['id']}/publish", json={"edit_revision": 1})
    body = {"problem_version_id": version["id"], "language": "c17", "source": "int main(){}"}
    assert student.get(f"/problems/{version['id']}").status_code == 403
    assert student.post("/submissions", json=body).status_code == 403
    assert student.post(f"/courses/{cid}/enroll").status_code == 200
    assert student.post("/submissions", json=body).status_code == 403
    body.update(exercise_context(teacher, student, monkeypatch, cid, version))
    assert student.post("/submissions", json=body).status_code == 202
    assert other.get(f"/author/problem-versions/{version['id']}").status_code == 404
    assert teacher.delete(f"/courses/{cid}/members/{user['id']}").status_code == 200
    assert student.post("/submissions", json=body).status_code == 404


def test_quota_and_audit_do_not_include_key_payload(client, monkeypatch):
    teacher, _ = account(client, "teacher_audit", "teacher")
    student, _ = account(client, "student_quota", "student")
    body = {'language': 'c17', 'source': 'int main(){}', **exercise_context(client, student, monkeypatch)}
    for _ in range(10):
        assert student.post("/runs", json=body).status_code == 202
    assert student.post("/runs", json=body).status_code == 429
    version = draft(teacher, course(teacher))
    teacher.get(f"/author/problem-versions/{version['id']}")
    with session() as db:
        rows = db.scalars(select(AuditEvent).where(AuditEvent.action == "problem.keys_read")).all()
        assert len(rows) == 1 and rows[0].details == {}
        assert "password" not in str([r.details for r in db.scalars(select(AuditEvent))])
