"""Self-check of timing integrity and non-disclosure; no application requests."""
import json
import os
from pathlib import Path
import tempfile

import timing as t
from launch import wrap
from analyze import span_records


class Example:
    def work(self, secret):
        return len(secret)


with tempfile.TemporaryDirectory() as directory:
    os.environ["JUDGE_PROFILE_DIR"] = directory
    os.environ["JUDGE_PROFILE_COMPONENT"] = "test"
    wrap(Example, "work", "example.work")
    assert Example().work("SECRET_NOT_LOGGED") == 17
    assert not list(Path(directory).glob("*.jsonl"))
    with t.trace("trace-1"):
        with t.span("parent"):
            assert Example().work("SECRET_NOT_LOGGED") == 17
            t.event("publication", task_id="child-message")
            try:
                with t.span("failure"):
                    raise ValueError("SECRET_NOT_LOGGED")
            except ValueError:
                pass
    contents = "".join(path.read_text() for path in Path(directory).glob("*.jsonl"))
    assert "SECRET_NOT_LOGGED" not in contents
    rows = [json.loads(line) for line in contents.splitlines()]
    spans = {row["name"]: row for row in rows if row["kind"] == "span"}
    assert spans["example.work"]["parent_id"] == spans["parent"]["span_id"]
    assert spans["failure"]["error"] == "ValueError"
    assert all(row["duration_ns"] >= 0 for row in spans.values())
    assert spans["parent"]["duration_ns"] >= spans["example.work"]["duration_ns"]
parent = dict(component='worker', pid=1, span_id='task', start_ns=100, end_ns=200)
commit = dict(component='worker', pid=1, span_id='commit', parent_id='task')
late = dict(component='worker', pid=1, parent_id='commit', at_ns=210)
unrelated = dict(component='worker', pid=1, parent_id='other', at_ns=150)
other_process = dict(component='worker', pid=2, parent_id='task', at_ns=150)
lookup = {('worker', 1, 'commit'): commit}
assert span_records([commit, late, unrelated, other_process], parent, lookup) == [commit, late]
print("PASS profiling spans, nesting, errors, secret exclusion, and joining commits despite clock drift")
