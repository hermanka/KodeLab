"""Join test-only timing records into an additive per-job critical path and diagnostic costs."""
from collections import Counter, defaultdict
import csv
from datetime import datetime
import json
import math
from pathlib import Path
import re
import statistics
import sys


def stats(values):
    values = sorted(values)
    if not values:
        return {"n": 0}
    return {"n": len(values), "mean": round(statistics.mean(values), 3), "median": round(statistics.median(values), 3),
            "p95": round(values[math.ceil(.95*len(values))-1], 3), "max": round(values[-1], 3)}


def span_records(rows, parent, lookup):
    selected = []
    for row in rows:
        if (row['component'], row['pid']) != (parent['component'], parent['pid']):
            continue
        ancestor = row
        while ancestor.get('parent_id'):
            if ancestor['parent_id'] == parent['span_id']:
                selected.append(row)
                break
            ancestor = lookup.get((row['component'], row['pid'], ancestor['parent_id']), {})
    return selected


def analyze(directory):
    raw = json.loads((directory/"results.json").read_text(encoding="utf-8-sig"))
    records = [json.loads(line) for file in (directory/"traces").glob("*.jsonl")
               for line in file.read_text(encoding="utf-8").splitlines() if line.strip()]
    grouped = defaultdict(list)
    for row in records:
        grouped[row["trace"]].append(row)

    def spans(rows, name):
        return [r for r in rows if r["kind"] == "span" and r["name"] == name]

    def events(rows, name):
        return [r for r in rows if r["kind"] == "event" and r["name"] == name]

    def ms(row):
        return row["duration_ns"]/1e6

    def direct(parent, row):
        return row["component"] == parent["component"] and row["pid"] == parent["pid"] and row.get("parent_id") == parent["span_id"]

    api_jobs = {r["attempt_id"]: r for r in records if r["name"] == "api.job"}
    span_lookup = {(r["component"], r["pid"], r["span_id"]): r for r in records if r["kind"] == "span"}
    jobs, executions, issues, measurement_notes = [], [], [], []
    for job in raw["jobs"]:
        try:
            identifier = job["attempt_id"]
            rows = grouped[identifier]
            worker = next(r for r in spans(rows, "worker.total") if any(direct(r, child) for child in spans(rows, "worker.runner_http")))
            remote = next(r for r in spans(rows, "worker.runner_http") if direct(worker, r))
            run = next(r for r in spans(rows, "runner.total") if not r["error"])
            publication = next(r for r in events(rows, "celery.publish_start") if r.get("task_id") == worker["task_id"])
            api_event = api_jobs[identifier]
            api_rows = grouped[api_event["trace"]]
            api = next(r for r in spans(api_rows, "api.create_submission") if r["span_id"] == api_event["parent_id"])
            # Span ancestry survives wall-clock adjustments that shift events beyond synthetic end_ns.
            api_rows = span_records(api_rows, api, span_lookup)
            api_commit = max(r["at_ns"] for r in events(api_rows, "db.committed"))
            commit_observation_lag = max(0, api_commit-publication["at_ns"])/1e6
            if commit_observation_lag:
                # SQL commit is visible before Python's after_commit hook may get CPU time.
                measurement_notes.append({"attempt_id": identifier, "type": "commit_observed_after_publication",
                    "overlap_ms": commit_observation_lag})
                api_commit = publication["at_ns"]
            worker_rows = span_records(rows, worker, span_lookup)
            result_commit = max(r["at_ns"] for r in events(worker_rows, "db.committed"))
            request_label = f"{job['phase']}_admission_wave_{len(job['http_attempts'])}"
            request = next(r for r in raw["requests"] if r["label"] == request_label and r["user"] == job["user"] and r["status"] == 202)
            origin = raw["summary"]["clock_origin_ns"]
            request_start = origin+round(request["start_s"]*1e9)
            initial_start = origin+round(job["submitted_s"]*1e9)
            seen = origin+round(job["completion_s"]*1e9)
            stages = {
                "api_until_commit_ms": (api_commit-api["start_ns"])/1e6,
                "outbox_wait_ms": (publication["at_ns"]-api_commit)/1e6,
                "broker_worker_wait_ms": (worker["start_ns"]-publication["at_ns"])/1e6,
                "worker_claim_load_ms": (remote["start_ns"]-worker["start_ns"])/1e6,
                "worker_runner_http_ms": ms(remote),
                "worker_validate_save_ms": (result_commit-remote["end_ns"])/1e6,
            }
            if any(value < -1 for value in stages.values()):
                issues.append({"attempt_id": identifier, "type": "negative_critical_path_interval", "stages": stages})
            closure = abs(sum(stages.values())-(result_commit-api["start_ns"])/1e6)
            assert closure < .01, f"Critical path closure error: {closure} ms"
            row = {"attempt_id": identifier, "phase": job["phase"], "language": job["language"], "mode": job["mode"],
                   "user": job["user"], "verdict": job["verdict"], **stages,
                   "http_admission_ms": request["latency_ms"], "api_handler_ms": ms(api),
                   "api_commit_observation_lag_ms": commit_observation_lag,
                   "request_pre_handler_ms": (api["start_ns"]-request_start)/1e6,
                   "api_lock_ms": sum(ms(r) for r in spans(api_rows, "db.admission_lock")),
                   "api_lock_held_ms": max(0, api_commit-max(r["end_ns"] for r in spans(api_rows, "db.admission_lock")))/1e6,
                   "api_health_ms": sum(ms(r) for r in spans(api_rows, "provider.health")),
                   "api_commit_ms": sum(ms(r) for r in spans(api_rows, "db.commit")),
                   "runner_total_ms": ms(run), "network_serialize_profile_flush_ms": ms(remote)-ms(run),
                   "result_validation_ms": sum(ms(r) for r in spans(worker_rows, "worker.validate_result")),
                   "request_to_db_ready_ms": (result_commit-request_start)/1e6,
                   "first_try_to_db_ready_ms": (result_commit-initial_start)/1e6,
                   "result_poll_lag_ms": (seen-result_commit)/1e6,
                   "request_to_client_ms": (seen-request_start)/1e6,
                   "first_try_to_client_ms": (seen-initial_start)/1e6,
                   "client_observed_ms": job["accepted_to_result_s"]*1000+request["latency_ms"],
                   "critical_path_closure_error_ms": closure}
            batch = span_lookup.get((publication["component"], publication["pid"], publication.get("parent_id")))
            if batch and batch["name"] == "dispatch.batch":
                beat = next((r for r in events(grouped[batch["trace"]], "celery.publish_start") if r.get("task") == "judgement.dispatch"), None)
                if beat:
                    row["scheduler_trigger_gap_ms"] = max(0, beat["at_ns"]-api_commit)/1e6
                    row["dispatcher_wait_after_commit_ms"] = max(0, batch["start_ns"]-max(beat["at_ns"], api_commit))/1e6
                    row["dispatcher_prepare_publish_ms"] = (publication["at_ns"]-max(batch["start_ns"], api_commit))/1e6
                    assert abs(row["scheduler_trigger_gap_ms"]+row["dispatcher_wait_after_commit_ms"]+
                               row["dispatcher_prepare_publish_ms"]-row["outbox_wait_ms"]) < .01
            for name in ("runner.container_create", "runner.attach_stdin", "runner.container_start", "runner.attach_output",
                         "runner.inspect", "runner.container_wait", "runner.container_remove", "runner.check_output",
                         "runner.update_limits"):
                row[name.replace("runner.", "")+"_ms"] = sum(ms(r) for r in spans(rows, name))
            run_execs = spans(rows, "runner.execute")
            row["execution_phase_count"] = len(run_execs)
            row["container_count"] = len(spans(rows, "runner.container_create"))
            row["inspect_count"] = len(spans(rows, "runner.inspect"))
            row["wait_count"] = len(spans(rows, "runner.container_wait"))
            row["start_count"] = len(spans(rows, "runner.container_start"))
            row["remove_count"] = len(spans(rows, "runner.container_remove"))
            child_total = 0
            row["run_after_stdin_approx_ms"] = 0
            row["run_before_stdin_approx_ms"] = 0
            for execution in run_execs:
                children = [r for r in rows if r["kind"] == "span" and direct(execution, r)]
                child_total += sum(ms(r) for r in children)
                values = {r["name"]: sum(ms(x) for x in children if x["name"] == r["name"]) for r in children}
                detail = {"attempt_id": identifier, "job_phase": job["phase"], "mode": job["mode"], "language": job["language"],
                    "phase": execution["phase"], "case_index": execution["case_index"],
                    "container_id": execution.get("container_id"), "execute_ms": ms(execution),
                    **values, "other_ms": ms(execution)-sum(values.values())}
                if execution["phase"] == "run":
                    first_inspect = min(r["start_ns"] for r in children if r["name"] == "runner.inspect")
                    first_wait = min(r["start_ns"] for r in children if r["name"] == "runner.container_wait")
                    # New runner waits immediately after stdin; final inspect is after exit.
                    observation = min(first_inspect, first_wait)
                    detail["input_observation_anchor"] = "wait_start" if first_wait < first_inspect else "inspect_start"
                    lifetime = next(r for r in events(rows, "sandbox.pid1_lifetime") if r["phase"] == "run" and r["case_index"] == execution["case_index"])
                    started = datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", lifetime["started_at"].replace("Z", "+00:00"))).timestamp()*1e9
                    finished = datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", lifetime["finished_at"].replace("Z", "+00:00"))).timestamp()*1e9
                    detail["after_stdin_approx_ms"] = max(0, finished-observation)/1e6
                    detail["before_stdin_approx_ms"] = max(0, observation-started)/1e6
                    row["run_after_stdin_approx_ms"] += detail["after_stdin_approx_ms"]
                    row["run_before_stdin_approx_ms"] += detail["before_stdin_approx_ms"]
                executions.append(detail)
            row["execute_other_ms"] = sum(ms(r) for r in run_execs)-child_total
            lifecycle_outside = sum(ms(r) for r in rows if r["kind"] == "span" and direct(run, r)
                                    and r["name"] in ("runner.container_create", "runner.container_remove"))
            row["runner_between_phases_ms"] = ms(run)-sum(ms(r) for r in run_execs)-lifecycle_outside
            row["compiler_wall_ms"] = sum(r["duration_ms"] for r in events(rows, "sandbox.compiler"))
            row["compiler_cpu_ms"] = sum(r["cpu_ms"] for r in events(rows, "sandbox.compiler"))
            row["compile_pid1_ms"] = sum(r["duration_ms"] for r in events(rows, "sandbox.pid1_lifetime") if r["phase"] == "compile")
            row["run_pid1_ms"] = sum(r["duration_ms"] for r in events(rows, "sandbox.pid1_lifetime") if r["phase"] == "run")
            row["lifecycle_create_start_remove_ms"] = row["container_create_ms"]+row["container_start_ms"]+row["container_remove_ms"]
            assert len(events(rows, "sandbox.compiler")) == 1, "Missing or duplicate compiler profile"
            assert len(events(rows, "sandbox.pid1_lifetime")) == row["execution_phase_count"], "Missing PID1 timing"
            expected_phases = 2 if job["mode"] == "run" else 6
            assert row["execution_phase_count"] == expected_phases, "Unexpected execution count"
            assert row["container_count"] in (1, expected_phases), "Unexpected physical container count"
            created = events(rows, "sandbox.created")
            if created and row["container_count"] == 1:
                assert all(r.get("container_id") == created[0]["container_id"] for r in run_execs), "Sandbox changed between phases"
            jobs.append(row)
        except (KeyError, StopIteration, AssertionError) as exc:
            issues.append({"type": "trace_join_failed", "phase": job["phase"], "user": job["user"], "message": str(exc)})

    numeric = sorted({key for row in jobs for key, value in row.items() if key.endswith("_ms")})
    groups = {}
    for name in sorted({j["phase"] for j in jobs}):
        rows = [j for j in jobs if j["phase"] == name]
        groups[name] = {"n": len(rows), "metrics_ms": {key: stats([j[key] for j in rows]) for key in numeric}}
    calibration = {}
    for label in ("unprofiled", "profiled"):
        rows = json.loads((directory/f"calibration-{label}.json").read_text())
        calibration[label] = {f"{language}_{mode}": stats([r["duration_ms"] for r in rows if r["language"] == language and r["mode"] == mode])
                              for language in ("c17", "cpp17") for mode in ("run", "judge")}
    dispatch = []
    for row in records:
        if row["name"] == "dispatch.batch" and row["kind"] == "span":
            published = next((r for r in grouped[row["trace"]] if r["name"] == "celery.publish_start" and r.get("task") == "judgement.dispatch"), None)
            if published:
                dispatch.append((row["start_ns"]-published["at_ns"])/1e6)
    result = {"trace_records": len(records), "jobs_requested": len(raw["jobs"]), "jobs_joined": len(jobs),
              "issues": issues, "measurement_notes": measurement_notes, "groups": groups, "calibration_ms": calibration,
              "dispatch_queue_delay_ms": stats(dispatch),
              "worker_deliveries": len([r for r in records if r["name"] == "worker.total" and r["kind"] == "span"]),
              "profile_errors": dict(Counter(r["error"] for r in records if r.get("error"))),
              "job_rows": jobs, "execution_rows": executions}
    (directory/"stage-analysis.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    for filename, rows in (("job-stages.csv", jobs), ("container-stages.csv", executions)):
        with (directory/filename).open("w", newline="", encoding="utf-8") as output:
            fields = sorted(set().union(*(row.keys() for row in rows))) if rows else ["empty"]
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader(); writer.writerows(rows)
    print(json.dumps({"records": len(records), "jobs": len(jobs), "requested": len(raw["jobs"]), "issues": issues}, indent=2))
    for name in ("run_30", "submit_30"):
        print(name, json.dumps({key: groups.get(name, {}).get("metrics_ms", {}).get(key) for key in (
            "outbox_wait_ms", "broker_worker_wait_ms", "runner_total_ms", "container_create_ms", "container_start_ms",
            "container_remove_ms", "compiler_wall_ms", "run_pid1_ms", "request_to_db_ready_ms")}))
    if issues or len(jobs) != len(raw["jobs"]):
        raise SystemExit("Incomplete trace analysis")


if __name__ == "__main__":
    analyze(Path(sys.argv[1]))
