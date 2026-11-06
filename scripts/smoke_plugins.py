"""Real plugin -> Celery -> runner integration. Deletes only its freshly-created class/plugin."""
import base64
import io
import json
from pathlib import Path
from uuid import uuid4
import zipfile

from client_helpers import admin_client, wait_for
from smoke import C_SUM, CPP_SUM


def main():
    admin = admin_client()
    plugin_id = "plugin-smoke-" + uuid4().hex[:8]
    cid = None
    installed = False
    try:
        example = Path("plugin/examples/sandbox-delegate")
        manifest = json.loads((example / "plugin.json").read_text())
        manifest.update(id=plugin_id, name="Isolated plugin smoke")
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("plugin.json", json.dumps(manifest))
            archive.writestr("plugin.py", (example / "plugin.py").read_text())
        response = admin.post("/admin/judge-plugins", json={"package_base64":base64.b64encode(data.getvalue()).decode(),"trusted_code":True})
        assert response.status_code == 201, "Plugin installation failed"
        installed = True
        revision = response.json()["active_revision"]
        assert admin.patch(f"/admin/judge-plugins/{plugin_id}",json={"enabled":True}).status_code==200
        assert plugin_id in admin.get("/providers").json()
        print("PASS ZIP installation, activation, dynamic discovery",flush=True)

        response=admin.post("/courses",json={"title":"Isolated plugin smoke","is_public":False})
        assert response.status_code==201
        cid=response.json()["id"]
        response=admin.post(f"/author/courses/{cid}/problems",json={
            "title":"Plugin sum","statement":"Read a and b, print their sum.","provider":plugin_id,
            "languages":["c17","cpp17"],"reference_solutions":{"c17":C_SUM,"cpp17":CPP_SUM},
            "cases":[{"input":"2 3\n","expected":"5\n","public":True},
                     {"input":"-7 -8\n","expected":"-15\n","public":False}]})
        assert response.status_code==201, "Plugin problem creation failed"
        version=response.json()
        url=f"/author/problem-versions/{version['id']}"
        response=admin.post(url+"/validate",json={"edit_revision":1})
        assert response.status_code==202
        result=wait_for(admin,f"/author/validations/{response.json()['id']}")
        assert result["valid"] and all(revision in row["environment"] for row in result["result"].values())
        assert admin.post(url+"/publish",json={"edit_revision":1}).status_code==200
        print("PASS plugin reference validation with real C17 and C++17 compilers",flush=True)

        for language,source in (("c17",C_SUM),("cpp17",CPP_SUM)):
            response=admin.post("/submissions",json={"problem_version_id":version["id"],"language":language,"source":source})
            assert response.status_code==202
            result=wait_for(admin,f"/submissions/{response.json()['id']}")
            assert result["verdict"]=="ACCEPTED" and result["score"]==100 and result["provider_revision"]==revision
            assert "stdout" not in result["result"]["cases"][1]
        response=admin.post("/runs",json={"problem_version_id":version["id"],"language":"cpp17","source":CPP_SUM,"input":"20 22\n"})
        assert response.status_code==202
        result=wait_for(admin,f"/submissions/{response.json()['id']}")
        assert result["verdict"]=="EXECUTED" and result["score"] is None and result["result"]["cases"][0]["stdout"].strip()=="42"
        print("PASS plugin grading, hidden-case filtering, custom input without score",flush=True)
        assert admin.patch(f"/admin/judge-plugins/{plugin_id}",json={"enabled":False}).status_code==200
        assert admin.delete(f"/admin/judge-plugins/{plugin_id}").status_code==409
        print("PASS deactivation and historical-reference uninstall guard",flush=True)
    finally:
        if cid:
            response=admin.request("DELETE",f"/courses/{cid}",json={"confirmation_title":"Isolated plugin smoke"})
            assert response.status_code==200, "New smoke class could not be cleaned; existing data was not touched"
        if installed:
            admin.patch(f"/admin/judge-plugins/{plugin_id}",json={"enabled":False})
            assert admin.delete(f"/admin/judge-plugins/{plugin_id}").status_code==200, "New smoke plugin could not be removed"
        admin.post("/auth/logout")
        admin.close()
    print("PASS isolated fixture cleanup; existing classes and plugins preserved",flush=True)


if __name__ == "__main__":
    main()
