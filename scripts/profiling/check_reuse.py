"""Functional Docker check of profiling one physical sandbox across three execution phases."""
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4

import uvicorn

import launch
from app.contracts import Case, JudgeRequest, Limits
from runner.engine import DockerRunner

identifier = uuid4()


def exercise(app, **kwargs):
    runner = DockerRunner(os.environ["SANDBOX_IMAGE"])
    try:
        result = runner.judge(JudgeRequest(attempt_id=identifier, language="c17", mode="judge",
            source='#include <stdio.h>\nint main(){int n;scanf("%d",&n);printf("%d\\n",n);}',
            limits=Limits(), cases=[Case(id=str(i), input=str(i), expected=str(i)) for i in (1, 2)]))
        assert result.verdict == "ACCEPTED"
    finally:
        runner.client.close()


with tempfile.TemporaryDirectory() as directory:
    os.environ.update(JUDGE_PROFILE_DIR=directory, JUDGE_PROFILE_COMPONENT="runner")
    uvicorn.run = exercise
    launch.runner()
    rows = [json.loads(line) for file in Path(directory).glob("*.jsonl") for line in file.read_text().splitlines()]
    created = [row for row in rows if row["name"] == "sandbox.created"]
    phases = [row for row in rows if row["name"] == "runner.execute"]
    assert len(created) == 1 and len(phases) == 3
    assert all(row["container_id"] == created[0]["container_id"] for row in phases)
    for name, count in (("runner.container_create", 1), ("runner.container_remove", 1),
                        ("runner.container_start", 3), ("sandbox.pid1_lifetime", 3),
                        ("runner.inspect", 3), ("runner.container_wait", 3)):
        assert sum(row["name"] == name for row in rows) == count, name
    assert all(not row.get("error") for row in rows)
print("PASS profiling one container, three phases, separate limits and PID1 lifetimes")
