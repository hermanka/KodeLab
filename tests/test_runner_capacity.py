"""Configured slots must be usable beyond the old four-slot/thread-pool limits."""
import os
import subprocess
import sys


def test_fifty_runner_slots_and_request_threads():
    code = '''
import asyncio
from types import SimpleNamespace
import anyio.to_thread
import runner.main as main

class FakeRunner:
    def __init__(self, image, warm=0):
        pass
    def close(self):
        pass
    def cleanup_expired(self):
        pass

main.DockerRunner = FakeRunner
assert main.slot_count == 50
for _ in range(50):
    assert main.slots.acquire(blocking=False)
assert not main.slots.acquire(blocking=False)
for _ in range(50):
    main.slots.release()

async def check():
    async with main.lifespan(main.app):
        assert anyio.to_thread.current_default_thread_limiter().total_tokens >= 50
asyncio.run(check())
'''
    result = subprocess.run([sys.executable, "-c", code],
        env={**os.environ, "RUNNER_SLOTS": "50", "RUNNER_TOKEN": "capacity-test-token-not-production"},
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_health_answers_while_every_slot_is_busy():
    # Regression: /health shared the thread pool with judges and timed out at full load.
    code = '''
import threading
import time
from types import SimpleNamespace
from uuid import uuid4
from fastapi.testclient import TestClient
import runner.main as main

release = threading.Event()

class FakeRunner:
    def __init__(self, image, warm=0):
        pass
    def close(self):
        pass
    def cleanup_expired(self):
        pass
    def health(self):
        pass
    def judge(self, request):
        assert release.wait(30)
        return {"verdict": "EXECUTED", "cases": [{"id": "c", "verdict": "EXECUTED"}]}

main.DockerRunner = FakeRunner
body = lambda: {"attempt_id": str(uuid4()), "language": "c17", "source": "int main(){}", "mode": "run",
                "limits": {}, "cases": [{"id": "c", "input": "", "public": True}]}
headers = {"X-Runner-Token": "capacity-test-token-not-production"}
with TestClient(main.app) as client:
    judges = [threading.Thread(target=client.post, args=("/judge",), kwargs={"json": body(), "headers": headers})
              for _ in range(main.slot_count)]
    for thread in judges:
        thread.start()
    for _ in range(200):
        if not main.slots._value:
            break
        time.sleep(0.05)
    assert main.slots._value == 0, "judges did not occupy every slot"
    answered = []
    probe = threading.Thread(target=lambda: answered.append(client.get("/health").status_code))
    probe.start()
    probe.join(timeout=3)
    while_busy = list(answered)
    release.set()
    for thread in judges:
        thread.join(timeout=10)
    probe.join(timeout=5)
    assert while_busy == [200], "health starved while slots were busy"
'''
    result = subprocess.run([sys.executable, "-c", code],
        env={**os.environ, "RUNNER_SLOTS": "50", "RUNNER_TOKEN": "capacity-test-token-not-production"},
        capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
