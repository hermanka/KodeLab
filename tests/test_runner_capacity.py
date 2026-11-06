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
    def __init__(self, image):
        self.client = SimpleNamespace(close=lambda: None)
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
