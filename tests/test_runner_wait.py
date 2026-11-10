"""The runner trusts one answer line from the bootstrap; anything else is an infrastructure failure, never a verdict."""
import json
import threading
from types import SimpleNamespace
from uuid import uuid4

import pytest

import runner.engine as engine
from app.contracts import JudgeRequest


def fake_container(frames, block=None):
    sent = []

    def stream():
        yield from frames
        if block:
            block.wait(5)

    return SimpleNamespace(
        sent=sent, start=lambda: None, attach=lambda **kwargs: stream(),
        attach_socket=lambda **kwargs: SimpleNamespace(
            _sock=SimpleNamespace(settimeout=lambda seconds: None, sendall=sent.append), close=lambda: None))


def test_answer_line_is_returned_without_waiting_for_the_container_to_exit():
    block = threading.Event()  # The stream stays open: the container has not exited yet.
    container = fake_container([(b'{"ok": ', None), (None, b"ignored stderr\n"), (b'true}\n', None)], block)
    try:
        assert engine.Sandbox(container).run({"source": "x"}, seconds=5) == {"ok": True}
    finally:
        block.set()
    assert container.sent == [b'{"source": "x"}\n']


@pytest.mark.parametrize("frames,blocks", [
    ([], False),                         # Bootstrap crashed: stream ended without an answer.
    ([(b'{"ok": tr', None)], False),     # Truncated answer.
    ([(None, b"Traceback\n")], False),   # Only stderr.
    ([], True),                          # No answer before the deadline.
])
def test_missing_or_late_answer_is_an_infrastructure_error(frames, blocks):
    block = threading.Event() if blocks else None
    try:
        with pytest.raises(RuntimeError, match="bootstrap failed"):
            engine.Sandbox(fake_container(frames, block)).run({}, seconds=0.2)
    finally:
        if block:
            block.set()


def test_oversized_answer_is_an_infrastructure_error(monkeypatch):
    monkeypatch.setattr(engine, "OUTPUT_LIMIT", 8)
    with pytest.raises(RuntimeError, match="bootstrap failed"):
        engine.Sandbox(fake_container([(b'{"ok": true}\n', None)])).run({}, seconds=1)


def case(**changes):
    return {"exit": 0, "timed_out": False, "output_exceeded": False, "cpu_ms": 5, "memory_exceeded": False,
            "stdout": "ok\n", "stderr": "", **changes}


@pytest.mark.parametrize("changes,expected", [
    ({}, "ACCEPTED"), ({"stdout": "no"}, "WRONG_ANSWER"), ({"exit": 3}, "RUNTIME_ERROR"), ({"exit": -11}, "RUNTIME_ERROR"),
    ({"exit": -24}, "TIME_LIMIT_EXCEEDED"), ({"cpu_ms": 2000}, "TIME_LIMIT_EXCEEDED"),
    ({"exit": -9, "timed_out": True}, "TIME_LIMIT_EXCEEDED"),
    ({"exit": -9}, "MEMORY_LIMIT_EXCEEDED"), ({"exit": -9, "memory_exceeded": True, "cpu_ms": 2000}, "MEMORY_LIMIT_EXCEEDED"),
    ({"exit": -9, "output_exceeded": True}, "OUTPUT_LIMIT_EXCEEDED")])
def test_one_start_carries_all_inputs_and_raw_results_map_to_verdicts(changes, expected):
    calls = []

    def run(payload, seconds):
        calls.append((payload, seconds))
        return {"ok": True, "log": "", "cases": [case(**changes), case()]}

    runner = engine.DockerRunner.__new__(engine.DockerRunner)
    runner.image_id = "image"
    request = JudgeRequest(attempt_id=uuid4(), language="c17", source="int main(){}", mode="judge",
                           limits={"time_seconds": 2, "memory_mb": 64},
                           cases=[{"id": "a", "input": "1", "expected": "ok"}, {"id": "b", "input": "2", "expected": "ok"}])
    result = runner.judge_in_sandbox(SimpleNamespace(run=run), request)
    assert [item.verdict for item in result.cases] == [expected, "ACCEPTED"] and result.verdict == expected
    (payload, seconds), = calls
    assert payload["inputs"] == ["1", "2"] and "expected" not in json.dumps(payload)
    assert payload["cpu_seconds"] == 2 and payload["wall_seconds"] == 5 and seconds == 10 + 2 * 5 + 10


def test_compilation_error_carries_the_log_and_no_cases():
    runner = engine.DockerRunner.__new__(engine.DockerRunner)
    runner.image_id = "image"
    request = JudgeRequest(attempt_id=uuid4(), language="c17", source="int main( {", mode="run",
                           limits={}, cases=[{"id": "a", "input": ""}])
    result = runner.judge_in_sandbox(SimpleNamespace(run=lambda payload, seconds: {"ok": False, "log": "error: x"}), request)
    assert result.verdict == "COMPILATION_ERROR" and result.compile_log == "error: x" and not result.cases
