"""N users press Run or Submit at the same instant; report what each of them waits for the result.

Full stack (API, queue, worker, runner, sandbox) with the editor's 0.4 s polling. Run inside the api container:
  <credentials JSON on stdin> | docker compose exec -T api python scripts/profiling/concurrent_users.py 12
Arguments: <users> [rounds=3]. Creates <users> teacher accounts and deactivates them afterwards.
Each round adds one Run, one C Submit and one C++ Submit per account on problem sum-v1.
"""
import statistics
import sys
import threading
import time

sys.path.insert(0, "/app/scripts")
from client_helpers import admin_client, make_user
from smoke import C_SUM, CPP_SUM

USERS = int(sys.argv[1])
ROUNDS = int(sys.argv[2]) if len(sys.argv) > 2 else 3
SCENARIOS = [("Run C", "/runs", "c17", C_SUM, {"input": "40 2\n"}, "EXECUTED"),
             ("Submit C", "/submissions", "c17", C_SUM, {}, "ACCEPTED"),
             ("Submit C++", "/submissions", "cpp17", CPP_SUM, {}, "ACCEPTED")]


def press(client, path, body, expected, barrier, waits, failures):
    barrier.wait()
    started = time.monotonic()
    try:
        response = client.post(path, json=body)
        assert response.status_code == 202, f"HTTP {response.status_code}"
        accepted = time.monotonic() - started
        row = response.json()
        while row["state"] not in ("completed", "system_error"):
            time.sleep(0.4)
            row = client.get(f"/submissions/{row['id']}").json()
        assert row["verdict"] == expected, f"{row['state']}/{row['verdict']}"
        waits.append((time.monotonic() - started, accepted))
    except Exception as exc:
        failures.append(str(exc))


def main():
    admin = admin_client()
    users = [make_user(admin, role="teacher") for _ in range(USERS)]
    try:
        for name, path, language, source, extra, expected in SCENARIOS:
            waits, failures = [], []
            for _ in range(ROUNDS):
                barrier = threading.Barrier(USERS)
                threads = [threading.Thread(target=press, args=(
                    client, path, {"language": language, "source": source, **extra}, expected, barrier, waits, failures))
                    for client, _ in users]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()
                time.sleep(12)  # Students do not burst back to back; lets the warm pool refill.
            assert not failures, f"{name}: {failures[:3]}"
            accepted = max(item[1] for item in waits)
            waits = sorted(item[0] for item in waits)
            print(f"{name}: {USERS} users x {ROUNDS} rounds, wait median={statistics.median(waits):.2f}s "
                  f"p95={waits[int(len(waits) * 0.95) - 1]:.2f}s max={waits[-1]:.2f}s "
                  f"(slowest request accepted after {accepted:.2f}s)", flush=True)
    finally:
        for _, user in users:
            admin.patch(f"/admin/users/{user['id']}", json={"is_active": False})


if __name__ == "__main__":
    main()
