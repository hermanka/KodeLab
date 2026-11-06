import base64
import io
import json
from pathlib import Path
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import session
from app.main import app
from app.models import Attempt, AuditEvent, JudgePluginVersion, ProblemVersion
from app.providers import ProviderUnavailable, provider_for
from app.tasks import run_attempt, run_validation
from tests.test_api_tasks import client
from tests.test_accounts_content import account, course, fake_judge, package, validate

EXAMPLE = Path(__file__).resolve().parent.parent / "plugin/examples/sandbox-delegate"


def plugin_zip(*, version="1.0.0", source=None, manifest=None, extra=None):
    manifest = manifest or json.loads((EXAMPLE / "plugin.json").read_text())
    manifest["version"] = version
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("plugin.json", json.dumps(manifest))
        archive.writestr("plugin.py", source if source is not None else (EXAMPLE / "plugin.py").read_text())
        for name, value in (extra or {}).items():
            archive.writestr(name, value)
    return {"package_base64": base64.b64encode(output.getvalue()).decode(), "trusted_code": True}


def install(admin, **kwargs):
    response = admin.post("/admin/judge-plugins", json=plugin_zip(**kwargs))
    assert response.status_code == 201, response.text
    return response.json()


def activate(admin, enabled=True, revision=None):
    response = admin.patch("/admin/judge-plugins/sandbox-delegate", json={"enabled": enabled, "revision": revision})
    assert response.status_code == 200, response.text
    return response.json()


def plugin_problem(teacher, cid):
    response = teacher.post(f"/author/courses/{cid}/problems", json={**package(), "provider": "sandbox-delegate"})
    assert response.status_code == 201, response.text
    return response.json()


def test_plugin_install_permissions_csrf_and_no_import(client):
    teacher, _ = account(client, "plugin_teacher", "teacher")
    student, _ = account(client, "plugin_student", "student")
    for other in (teacher, student, TestClient(app)):
        assert other.get("/admin/judge-plugins").status_code in (401, 403)
        assert other.post("/admin/judge-plugins", json=plugin_zip()).status_code in (401, 403)
        assert other.patch("/admin/judge-plugins/sandbox-delegate", json={"enabled":True}).status_code in (401, 403)
        assert other.delete("/admin/judge-plugins/sandbox-delegate").status_code in (401, 403)
    browser = TestClient(app)
    browser.post("/auth/login", json={"username":"test_admin","password":"test-password-long-enough"})
    assert browser.post("/admin/judge-plugins", json=plugin_zip()).status_code == 403
    source = "raise RuntimeError('Must not execute in API')\n" + (EXAMPLE / "plugin.py").read_text()
    row = install(client, source=source)
    assert not row["enabled"]
    assert "source" not in json.dumps(row)
    assert "sandbox-delegate" not in teacher.get("/providers").json()
    activate(client)
    assert teacher.get("/providers").json()["sandbox-delegate"]["implemented"]
    plugin_problem(teacher, course(teacher))  # Draft save also must not import source.
    assert "Must not execute" not in client.get("/admin/judge-plugins").text


@pytest.mark.parametrize("change", ["path", "bomb", "syntax", "reserved", "api", "method", "empty", "invalid-base64", "encrypted", "duplicate"])
def test_reject_invalid_packages_without_installing(client, change):
    manifest = json.loads((EXAMPLE / "plugin.json").read_text())
    kwargs = {}
    if change == "path": kwargs["extra"] = {"../escape.py":"pass"}
    if change == "bomb": kwargs["extra"] = {"README.md":"x" * 262145}
    if change == "syntax": kwargs["source"] = "class Plugin("
    if change == "empty": kwargs["source"] = ""
    if change == "method": kwargs["source"] = "class Plugin:\n    async def judge(self, request): pass\n"
    if change == "reserved": manifest["id"] = "custom"
    if change == "api": manifest["api_version"] = 999
    kwargs["manifest"] = manifest
    body = plugin_zip(**kwargs)
    if change == "invalid-base64": body["package_base64"] = "***"
    if change in ("duplicate", "encrypted"):
        raw = base64.b64decode(body["package_base64"])
        if change == "duplicate":
            buffer = io.BytesIO(raw)
            with zipfile.ZipFile(buffer, "a") as archive:
                archive.writestr("plugin.py", "pass")
            raw = buffer.getvalue()
        else:
            raw = bytearray(raw)
            # Set encrypted bit on the first central directory entry.
            offset = raw.index(b"PK\x01\x02")
            raw[offset+8] |= 1
        body["package_base64"] = base64.b64encode(raw).decode()
    assert client.post("/admin/judge-plugins", json=body).status_code == 422
    assert client.get("/admin/judge-plugins").json() == []


def test_version_pinning_validation_submission_and_disabled_queue(client, monkeypatch):
    first = install(client)
    activate(client)
    teacher, _ = account(client, "plugin_author", "teacher")
    cid = course(teacher)
    version = plugin_problem(teacher, cid)
    fake_judge(monkeypatch)
    validation = validate(teacher, version)
    assert validation["valid"]
    second = install(client, version="2.0.0", source=(EXAMPLE / "plugin.py").read_text().replace(
        "return self.context.run_custom(request)", "raise RuntimeError('new version must not run old jobs')"))
    assert second["active_revision"] == first["active_revision"]
    activate(client, revision=second["versions"][0]["revision"])
    result = teacher.post(f"/author/problem-versions/{version['id']}/publish", json={"edit_revision":1})
    assert result.status_code == 200, result.text
    assert result.json()["provider_revision"] == first["active_revision"]
    assert result.json()["provider_version"] == "1.0.0"
    submission = client.post("/submissions", json={"problem_version_id":version["id"],"language":"c17","source":"int main(){}"})
    assert submission.status_code == 202, submission.text
    row = submission.json()
    assert row["provider_revision"] == first["active_revision"]
    activate(client, enabled=False)
    assert client.post("/submissions", json={"problem_version_id":version["id"],"language":"c17","source":"int main(){}"}).status_code == 503
    run_attempt.run(row["attempt_id"])
    judged = client.get(f"/submissions/{row['id']}").json()
    assert judged["state"] == "completed" and judged["score"] == 100
    assert first["active_revision"] in judged["result"]["environment"]
    assert "stdout" not in judged["result"]["cases"][1]
    assert client.delete("/admin/judge-plugins/sandbox-delegate").status_code == 409
    with session() as db:
        assert db.get(Attempt,row["attempt_id"]).snapshot["provider_revision"] == first["active_revision"]
        assert len(db.scalars(select(JudgePluginVersion)).all()) == 2
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "judge_plugin.installed"))


def test_inactive_duplicate_uninstall_and_runtime_guard(client):
    install(client)
    assert client.post("/admin/judge-plugins", json=plugin_zip()).status_code == 409
    assert client.post("/admin/judge-plugins", json={**plugin_zip(),"trusted_code":False}).status_code == 422
    with pytest.raises(ProviderUnavailable): provider_for("sandbox-delegate")
    activate(client)
    assert client.delete("/admin/judge-plugins/sandbox-delegate").status_code == 409
    with pytest.raises(ProviderUnavailable):
        provider_for("sandbox-delegate").submit(None,"x")
    activate(client,False)
    assert client.delete("/admin/judge-plugins/sandbox-delegate").status_code == 200
    assert client.get("/admin/judge-plugins").json() == []


def test_bad_plugin_results_retry_without_zero(client, monkeypatch):
    # Syntactically valid packages can fail at runtime; preserve infrastructure semantics.
    source = (EXAMPLE / "plugin.py").read_text().replace("return self.context.run_custom(request)", "return {'verdict':'ACCEPTED','cases':[]}")
    install(client, source=source); activate(client)
    with session() as db, db.begin():
        version=db.get(ProblemVersion,"sum-v1")
        version.provider="sandbox-delegate"
    row=client.post("/submissions",json={"language":"c17","source":"int main(){}"}).json()
    for state in ("retry_pending","retry_pending","system_error"):
        run_attempt.run(row["attempt_id"])
        result=client.get(f"/submissions/{row['id']}").json()
        assert result["state"]==state and result["score"] is None


def test_validation_queued_before_update_or_disable_uses_original_plugin(client, monkeypatch):
    first=install(client); activate(client)
    teacher,_=account(client,"plugin_queued","teacher")
    version=plugin_problem(teacher,course(teacher))
    queued=teacher.post(f"/author/problem-versions/{version['id']}/validate",json={"edit_revision":1}).json()
    install(client,version="1.1.0",source="raise RuntimeError('not old version')\n"+(EXAMPLE/"plugin.py").read_text())
    activate(client,False)
    fake_judge(monkeypatch)
    run_validation.run(queued["id"])
    result=teacher.get(f"/author/validations/{queued['id']}").json()
    assert result["state"]=="completed" and result["valid"]
    assert teacher.post(f"/author/problem-versions/{version['id']}/publish",json={"edit_revision":1}).status_code==503
    assert first["active_revision"] in result["result"]["c17"]["environment"]


def test_plugin_student_completion_and_provider_override_guard(client, monkeypatch):
    install(client); activate(client)
    teacher,_=account(client,"plugin_learning_teacher","teacher")
    student,_=account(client,"plugin_learning_student","student")
    cid=course(teacher,public=True)
    version=plugin_problem(teacher,cid)
    fake_judge(monkeypatch)
    assert validate(teacher,version)["valid"]
    assert teacher.post(f"/author/problem-versions/{version['id']}/publish",json={"edit_revision":1}).status_code==200
    response=teacher.post(f"/author/courses/{cid}/paths",json={"title":"Plugin path","steps":[
        {"key":"exercise","title":"Sum","kind":"exercise","problem_version_id":version["id"]}]})
    assert response.status_code==201
    path=response.json()
    assert teacher.post(f"/author/path-versions/{path['id']}/publish",json={"edit_revision":1}).status_code==200
    enrollment=student.post(f"/paths/{path['path_id']}/enroll").json()
    body={"problem_version_id":version["id"],"language":"c17","source":"int main(){}",
          "enrollment_id":enrollment["id"],"path_step_id":enrollment["steps"][0]["id"]}
    assert student.post("/submissions",json={**body,"provider":"custom"}).status_code==403
    row=student.post("/submissions",json=body).json()
    run_attempt.run(row["attempt_id"])
    result=student.get(f"/enrollments/{enrollment['id']}").json()
    assert result["progress"]==100 and result["score"]==100 and result["complete"]
    assert student.get(f"/courses/{cid}/leaderboard").json()["rows"][0]["score"]==100
