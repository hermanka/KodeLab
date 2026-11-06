"""Test-only spans. Explicit metadata only; never serialize source, inputs, or credentials."""
from contextlib import contextmanager
from contextvars import ContextVar
import itertools
import json
import os
from pathlib import Path
import sys
import threading
import time

current = ContextVar("judge_profile", default=None)
sequence = itertools.count()
write_lock = threading.Lock()


def write(rows):
    directory = os.getenv("JUDGE_PROFILE_DIR")
    if not directory or not rows:
        return
    component = os.getenv("JUDGE_PROFILE_COMPONENT", "test")
    path = Path(directory) / f"{component}-{os.getpid()}.jsonl"
    payload = "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows)
    with write_lock:
        with path.open("a", encoding="utf-8") as output:
            output.write(payload)


def event(name, *, trace=None, **metadata):
    context = current.get()
    row = {"kind": "event", "name": name, "trace": trace or (context["trace"] if context else None),
           "at_ns": time.time_ns(), "component": os.getenv("JUDGE_PROFILE_COMPONENT", "test"),
           "pid": os.getpid(), **metadata}
    if context:
        row.update(parent_id=context["stack"][-1] if context["stack"] else None, **context["fields"])
        row.update(metadata)
        context["buffer"].append(row)
    else:
        write([row])


@contextmanager
def trace(identifier, **metadata):
    context = {"trace": str(identifier), "fields": metadata, "buffer": [], "stack": []}
    token = current.set(context)
    try:
        yield context
    finally:
        current.reset(token)
        try:
            write(context["buffer"])
        except OSError as exc:
            print("PROFILE_WRITE_FAILED " + type(exc).__name__, file=sys.stderr)


@contextmanager
def fields(**metadata):
    context = current.get()
    if not context:
        yield
        return
    previous = context["fields"]
    context["fields"] = {**previous, **metadata}
    try:
        yield
    finally:
        context["fields"] = previous


@contextmanager
def span(name, **metadata):
    context = current.get()
    if not context:
        yield
        return
    identifier = f"{os.getpid()}-{next(sequence)}"
    parent = context["stack"][-1] if context["stack"] else None
    context["stack"].append(identifier)
    start_ns, start_mono = time.time_ns(), time.perf_counter_ns()
    error = None
    try:
        yield
    except BaseException as exc:
        error = type(exc).__name__
        raise
    finally:
        duration = time.perf_counter_ns()-start_mono
        context["stack"].pop()
        context["buffer"].append({"kind": "span", "name": name, "trace": context["trace"],
            "span_id": identifier, "parent_id": parent, "start_ns": start_ns,
            "duration_ns": duration, "end_ns": start_ns+duration, "error": error,
            "component": os.getenv("JUDGE_PROFILE_COMPONENT", "test"), "pid": os.getpid(),
            **context["fields"], **metadata})
