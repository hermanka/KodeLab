"""Real MariaDB/Redis/GCC authoring-to-submission integration; run via test-integration.ps1."""
from concurrent.futures import ThreadPoolExecutor

from client_helpers import admin_client, make_user, wait_for
from smoke import C_SUM, CPP_SUM


def main():
    admin = admin_client()
    teacher, _ = make_user(admin, "teacher")
    other_teacher, _ = make_user(admin, "teacher")
    student, learner = make_user(admin)
    stranger, _ = make_user(admin)
    response = teacher.post("/courses", json={"title": "Integration C/C++", "is_public": False})
    assert response.status_code == 201
    course_id = response.json()["id"]
    assert teacher.post(f"/courses/{course_id}/members", json={"user_id": learner["id"]}).status_code == 201
    response = teacher.post(f"/author/courses/{course_id}/lessons", json={
        "title": "Penjumlahan", "body_markdown": "# Belajar\n<script>alert(1)</script>\nGunakan input/output."})
    assert response.status_code == 201
    lesson = response.json()
    assert "<script>" not in lesson["body_html"]
    assert student.get(f"/courses/{course_id}/lessons").json() == []
    assert teacher.post(f"/author/lesson-versions/{lesson['id']}/publish", json={"edit_revision": 1}).status_code == 200
    assert len(student.get(f"/courses/{course_id}/lessons").json()) == 1
    print("PASS dynamic material publication and safe rendering", flush=True)

    package = {"title": "Jumlah dinamis", "statement": "Baca dua bilangan, cetak jumlahnya.",
               "languages": ["c17", "cpp17"], "cases": [
                   {"input": "2 3\n", "expected": "5\n", "public": True},
                   {"input": "-7 -8\n", "expected": "-15\n", "public": False}],
               "reference_solutions": {"c17": C_SUM, "cpp17": CPP_SUM}}
    response = teacher.post(f"/author/courses/{course_id}/problems", json=package)
    assert response.status_code == 201, response.text
    version = response.json()
    url = f"/author/problem-versions/{version['id']}"
    assert student.get(f"/problems/{version['id']}").status_code == 404
    assert teacher.post(url + "/publish", json={"edit_revision": 1}).status_code == 409
    response = teacher.post(url + "/validate", json={"edit_revision": 1})
    assert response.status_code == 202
    assert teacher.put(url, json={**package, "edit_revision": 1}).status_code == 409
    validation = wait_for(teacher, f"/author/validations/{response.json()['id']}")
    assert validation["valid"] and set(validation["result"]) == {"c17", "cpp17"}
    assert teacher.post(url + "/publish", json={"edit_revision": 1}).status_code == 200
    print("PASS reference C17/C++17 sandbox validation and problem publication", flush=True)

    public = teacher.get(f"/problems/{version['id']}").json()
    assert len(public["samples"]) == 1 and "reference_solutions" not in public and "cases" not in public
    assert student.get(url).status_code == 404
    assert other_teacher.get(url).status_code == 404
    assert stranger.get(f"/problems/{version['id']}").status_code == 403
    path = teacher.post(f"/author/courses/{course_id}/paths", json={"title": "Integration path", "steps": [{"key": "sum", "title": "Sum", "kind": "exercise", "problem_version_id": version["id"]}]}).json()
    assert teacher.post(f"/author/path-versions/{path['id']}/publish", json={"edit_revision": 1}).status_code == 200
    e = student.post(f"/paths/{path['path_id']}/enroll").json()
    response = student.post("/submissions", json={"problem_version_id": version["id"], "language": "cpp17", "source": CPP_SUM, "enrollment_id": e["id"], "path_step_id": e["steps"][0]["id"]})
    assert response.status_code == 202
    submission_id = response.json()["id"]
    result = wait_for(student, f"/submissions/{submission_id}")
    assert result["verdict"] == "ACCEPTED" and result["score"] == 100
    assert "stdout" not in result["result"]["cases"][1]
    assert stranger.get(f"/submissions/{submission_id}").status_code == 404
    assert other_teacher.get(f"/submissions/{submission_id}").status_code == 404
    assert teacher.get(f"/submissions/{submission_id}").status_code == 200
    assert teacher.get(f"/submissions?course_id={course_id}").json()[0]["id"] == submission_id
    assert student.get(f"/submissions?course_id={course_id}").status_code == 404
    assert teacher.get(f"/courses/{course_id}/members").json()[0]["id"] == learner["id"]
    print("PASS enrolled submission, ownership, class scope, and key confidentiality", flush=True)

    revision = teacher.post(f"/author/problems/{version['problem_id']}/versions").json()
    assert revision["revision"] == 2
    bad_package = {**package, "cases": [package["cases"][0], {"input": "-7 -8\n", "expected": "999\n"}]}
    revised_url = f"/author/problem-versions/{revision['id']}"
    response = teacher.put(revised_url, json={**bad_package, "edit_revision": 1})
    assert response.status_code == 200
    response = teacher.post(revised_url + "/validate", json={"edit_revision": 2})
    assert response.status_code == 202
    validation = wait_for(teacher, f"/author/validations/{response.json()['id']}")
    assert validation["valid"] is False
    assert teacher.post(revised_url + "/publish", json={"edit_revision": 2}).status_code == 409
    assert student.get(f"/problems/{version['id']}").status_code == 403
    print("PASS incorrect key rejection and published-version preservation", flush=True)

    # An isolated account plus long-running jobs makes concurrent admission observable
    # before any of the ten allowed pending runs finishes.
    quota_client, _ = make_user(admin, role="teacher")

    def send_run(_):
        return quota_client.post("/runs", json={"language": "c17", "source": "int main(){for(;;){}}"})

    with ThreadPoolExecutor(max_workers=12) as pool:
        responses = list(pool.map(send_run, range(12)))
    assert sum(r.status_code == 202 for r in responses) == 10
    assert sum(r.status_code == 429 for r in responses) == 2
    for response in responses:
        if response.status_code == 202:
            row = wait_for(quota_client, f"/submissions/{response.json()['id']}")
            assert row["verdict"] == "TIME_LIMIT_EXCEEDED"
    print("PASS concurrent MariaDB admission quota: 10 admitted, 2 rejected", flush=True)
    print("Authoring/account integration checks passed.")


if __name__ == "__main__":
    main()
