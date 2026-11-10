"""Deterministic deadline races must not produce a false participant verdict."""
from types import SimpleNamespace

from docker.errors import APIError
import pytest

import runner.engine as engine


@pytest.mark.parametrize("scenario,expected_timeout,expected_inspections", [
    ("normal", False, 1), ("timeout", True, 1), ("exit_race", False, 2)])
def test_wait_instead_of_polling_and_deadline_exit_race(monkeypatch, scenario, expected_timeout, expected_inspections):
    container, timer = fake_execution(monkeypatch, scenario)
    result = engine.DockerRunner.__new__(engine.DockerRunner).execute(container, "run", {}, 1, 64, 1024)
    assert result.timed_out is expected_timeout
    assert container.inspections == expected_inspections
    assert container.wait_calls == 1
    assert timer[0].cancelled and timer[0].joined


@pytest.mark.parametrize("scenario", ["wait_failure", "kill_failure"])
def test_monitoring_failure_is_infrastructure_error_and_cancels_timer(monkeypatch, scenario):
    container, timer = fake_execution(monkeypatch, scenario)
    with pytest.raises(RuntimeError, match="wait failure|deadline enforcement failed"):
        engine.DockerRunner.__new__(engine.DockerRunner).execute(container, "run", {}, 1, 64, 1024)
    assert timer[0].cancelled and timer[0].joined


def fake_execution(monkeypatch, scenario):
    timers = []

    class Timer:
        def __init__(self, seconds, callback):
            self.callback = callback
            self.cancelled = self.joined = False
            timers.append(self)
        def start(self):
            pass
        def cancel(self):
            self.cancelled = True
        def join(self):
            self.joined = True

    class Container:
        inspections = wait_calls = 0
        status = "running"
        attrs = {"State": {"ExitCode": 0, "OOMKilled": False}}
        def update(self, **kwargs):
            pass
        def attach_socket(self, **kwargs):
            return SimpleNamespace(_sock=SimpleNamespace(settimeout=lambda n: None, sendall=lambda b: None), close=lambda: None)
        def attach(self, **kwargs):
            return (item for item in ())
        def start(self):
            pass
        def kill(self):
            if scenario == "exit_race":
                raise APIError("Already exited")
            if scenario == "kill_failure":
                raise RuntimeError("Docker unavailable")
            self.status = "exited"
            self.attrs = {"State": {"ExitCode": 137, "OOMKilled": False}}
        def reload(self):
            self.inspections += 1
        def wait(self, *, timeout, condition):
            self.wait_calls += 1
            assert condition == "not-running" and timeout > 1
            if scenario == "wait_failure":
                raise RuntimeError("wait failure")
            if scenario == "exit_race":
                self.status = "exited"
            if scenario in ("timeout", "exit_race", "kill_failure"):
                timers[0].callback()
            self.status = "exited"
            return {"StatusCode": self.attrs["State"]["ExitCode"]}

    monkeypatch.setattr(engine.threading, "Timer", Timer)
    return Container(), timers


@pytest.mark.parametrize("code,oom,expected", [
    (137, False, "TIME_LIMIT_EXCEEDED"), (137, True, "MEMORY_LIMIT_EXCEEDED"), (139, False, "RUNTIME_ERROR")])
def test_cpu_limit_kill_is_time_limit_and_wall_clock_is_only_a_backstop(code, oom, expected):
    import json
    from app.contracts import JudgeRequest
    from uuid import uuid4
    calls = []

    def execute(container, phase, payload, seconds, memory_mb, output_limit):
        calls.append((phase, payload, seconds))
        if phase == "compile":
            out = json.dumps({"ok": True, "log": "", "binary": "AA=="}).encode()
            return engine.Execution(0, out, b"", 10, False, False, False)
        return engine.Execution(code, b"", b"", 10, False, False, oom)

    runner = engine.DockerRunner.__new__(engine.DockerRunner)
    runner.image_id, runner.execute = "image", execute
    request = JudgeRequest(attempt_id=uuid4(), language="c17", source="int main(){}", mode="judge",
                           limits={"time_seconds": 2}, cases=[{"id": "c", "input": "", "expected": ""}])
    assert runner.judge_in_sandbox(None, request).verdict == expected
    phase, payload, seconds = calls[1]
    assert phase == "run" and payload["cpu_seconds"] == 2 and seconds == 8
