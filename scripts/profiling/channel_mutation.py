"""Mutation check for the cross-case channel tests (paper, bagian 4.1 "Analisis mutasi").

Runs the inotify and memory scenarios from tests/test_sandbox_reuse.py against the real bootstrap and two
broken copies of it: without the kill sweep (M2) and without the wipe (M3). Each test must fail exactly when
the mechanism it targets is removed. Production code is not changed: the mutant bootstrap is passed to the
sandbox image with `python3 -c`, inside the production container configuration.

Run inside the runner container (Docker SDK + socket):
  docker compose run --rm --no-deps -T runner python scripts/profiling/channel_mutation.py [repeats] [out.json]
"""
import json
import os
import re
import sys
import time
from pathlib import Path

from docker.models.containers import ContainerCollection

from app.contracts import Case, JudgeRequest, Limits
from runner.engine import DockerRunner

REPEATS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else None
IMAGE = os.environ.get("SANDBOX_IMAGE", "judgementsystem-sandbox:gcc12-v4")
TESTS = Path(__file__).resolve().parents[2] / "tests" / "test_sandbox_reuse.py"

SWEEP = "        stream.close()\n        sweep()\n"
WIPE = "    wipe()  # Also restores the executable"


def source_of(test_name):
    text = TESTS.read_text(encoding="utf-8")
    body = text[text.index(f"def {test_name}("):]
    return re.search(r"source = r'''(.*?)'''", body, re.S).group(1)


def mutants(original):
    assert SWEEP in original and WIPE in original, "mutation points not found: bootstrap changed, update this script"
    return {
        "original": original,
        "no_sweep_M2": original.replace(SWEEP, "        stream.close()\n        pass  # MUTANT: no kill sweep (M2)\n"),
        "no_wipe_M3": original.replace(WIPE, "    [os.unlink(p) for p in ('/work/main', '/work/stdin') if os.path.exists(p)]  # MUTANT: no wipe (M3)"),
    }


def run(runner, bootstrap, source, inputs):
    """One job in the production container configuration, with the given bootstrap as PID 1."""
    # client.containers is a new collection on every access, so patch the class for the duration of this job.
    create = ContainerCollection.create
    ContainerCollection.create = lambda self, *args, **kwargs: create(self, *args, entrypoint=["python3", "-I", "-c", bootstrap], **kwargs)
    try:
        request = JudgeRequest(attempt_id=__import__("uuid").uuid4(), language="c17", source=source, mode="run",
                               limits=Limits(time_seconds=1, memory_mb=64, output_bytes=1024),
                               cases=[Case(id=str(i), input=v, public=True) for i, v in enumerate(inputs)])
        result = runner.judge(request)
    finally:
        ContainerCollection.create = create
    return [case.stdout.strip() or f"[{case.verdict}]" for case in result.cases]


def main():
    runner = DockerRunner(IMAGE)
    try:
        original = runner.client.containers.run(IMAGE, entrypoint=["cat", "/opt/judge/entrypoint.py"], remove=True).decode()
        variants = mutants(original)
        scenarios = {
            "inotify": (source_of("test_inotify_watcher_cannot_carry_hidden_input_to_a_later_case"),
                        ["watch", "SECRET-HIDDEN-INPUT", "check"]),
            "memory": (source_of("test_memory_charged_by_one_case_is_released_before_the_next"), ["1", "2"]),
        }
        rows = []
        for repeat in range(REPEATS):
            for variant, bootstrap in variants.items():
                for scenario, (source, inputs) in scenarios.items():
                    outputs = run(runner, bootstrap, source, inputs)
                    rows.append({"repeat": repeat, "variant": variant, "scenario": scenario, "outputs": outputs})
                    print(f"{variant:<12} {scenario:<8} {' | '.join(outputs)}", flush=True)
                    time.sleep(0.5)
    finally:
        runner.close()

    def verdict(row):
        out = row["outputs"]
        if row["scenario"] == "inotify":
            return "leak" if out[-1].startswith("leaked") else ("no_leak" if out[-1] == "nothing" else "invalid")
        try:
            start1, after1 = map(int, out[0].split())
            start2 = int(out[1].split()[0])
        except (ValueError, IndexError):
            return "invalid"
        if after1 - start1 < 40:
            return "invalid"
        return "retained" if start2 - start1 >= 16 else "released"

    expected = {("original", "inotify"): "no_leak", ("original", "memory"): "released",
                ("no_sweep_M2", "inotify"): "leak", ("no_sweep_M2", "memory"): "released",
                ("no_wipe_M3", "inotify"): "no_leak", ("no_wipe_M3", "memory"): "retained"}
    for row in rows:
        row["observed"] = verdict(row)
        row["expected"] = expected[(row["variant"], row["scenario"])]
    wrong = [r for r in rows if r["observed"] != r["expected"]]
    summary = {"image": IMAGE, "repeats": REPEATS, "rows": rows, "all_as_expected": not wrong}
    if OUT:
        OUT.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print("\nall outcomes as expected" if not wrong else f"\nUNEXPECTED: {[(r['variant'], r['scenario'], r['observed']) for r in wrong]}")
    sys.exit(1 if wrong else 0)


if __name__ == "__main__":
    main()
