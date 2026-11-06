"""Run inside the api container against the complete Compose deployment."""
import time
from uuid import uuid4

import httpx
from client_helpers import admin_client, make_user

C_SUM = '#include <stdio.h>\nint main(void){int a,b;scanf("%d%d",&a,&b);printf("%d\\n",a+b);return 0;}'
CPP_SUM = '#include <iostream>\nint main(){int a,b;std::cin>>a>>b;std::cout<<a+b<<"\\n";}'
ISOLATION = '''#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
int main(void) {
    int denied = open("/etc/judgement-write-probe", O_CREAT|O_WRONLY, 0600) == -1;
    printf("%d %d %d %d\\n", (int)getuid(), denied,
           access("/var/run/docker.sock", F_OK) == -1, getenv("RUNNER_TOKEN") == NULL);
    return 0;
}'''


def main():
    admin = admin_client()
    client, _ = make_user(admin, role="teacher")
    assert client.get("/health/ready").status_code == 200
    assert httpx.get("http://localhost:8000/problems").status_code in (401, 403)
    assert len(client.get("/problems/sum-v1").json()["samples"]) == 1
    assert client.get("/providers").json()["domjudge"]["implemented"] is False
    body = {"language": "c17", "source": C_SUM, "provider": "domjudge"}
    assert admin.post("/submissions", json=body).status_code == 422
    jobs = []
    for label, language, source, expected in [
        ("C17 correct", "c17", C_SUM, "ACCEPTED"),
        ("C++17 correct", "cpp17", CPP_SUM, "ACCEPTED"),
        ("hardcoded", "c17", '#include <stdio.h>\nint main(){puts("5");}', "WRONG_ANSWER"),
        ("compile error", "cpp17", "int main( {", "COMPILATION_ERROR"),
        ("runtime error", "c17", "int main(){return 7;}", "RUNTIME_ERROR"),
        ("infinite loop", "c17", "int main(){for(;;){}}", "TIME_LIMIT_EXCEEDED"),
        ("output flood", "cpp17", '#include <cstdio>\nint main(){for(;;)puts("0123456789");}', "OUTPUT_LIMIT_EXCEEDED"),
    ]:
        key = str(uuid4())
        body = {"language": language, "source": source}
        response = client.post("/submissions", json=body, headers={"Idempotency-Key": key})
        assert response.status_code == 202, response.text
        submission_id = response.json()["id"]
        repeated = client.post("/submissions", json=body, headers={"Idempotency-Key": key})
        assert repeated.json()["id"] == submission_id
        conflict = client.post("/submissions", json={**body, "source": source + "\n"}, headers={"Idempotency-Key": key})
        assert conflict.status_code == 409
        jobs.append((label, submission_id, expected))
    response = client.post("/runs", json={"language": "cpp17", "source": CPP_SUM, "input": "40 2\n"})
    assert response.status_code == 202, response.text
    jobs.append(("custom input", response.json()["id"], "EXECUTED"))
    response = client.post("/runs", json={"language": "c17", "source": ISOLATION, "input": ""})
    assert response.status_code == 202, response.text
    jobs.append(("sandbox isolation", response.json()["id"], "EXECUTED"))
    deadline = time.monotonic() + 200
    while jobs:
        assert time.monotonic() < deadline, f"Jobs did not finish: {jobs}"
        for job in jobs[:]:
            label, submission_id, expected = job
            row = client.get(f"/submissions/{submission_id}").json()
            assert row["state"] != "system_error", (label, row)
            if row["state"] != "completed":
                continue
            assert row["verdict"] == expected, (label, row)
            assert row["score"] == (None if expected == "EXECUTED" else 100 if expected == "ACCEPTED" else 0)
            if expected == "EXECUTED":
                expected_output = "65534 1 1 1" if label == "sandbox isolation" else "42"
                assert row["result"]["cases"][0]["stdout"].strip() == expected_output
            elif row["result"]["cases"]:
                assert "stdout" not in row["result"]["cases"][1]
            print(f"PASS {label}: {expected}", flush=True)
            jobs.remove(job)
        time.sleep(1)
    print("End-to-end smoke checks passed.")


if __name__ == "__main__":
    main()
