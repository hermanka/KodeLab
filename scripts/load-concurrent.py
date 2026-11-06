"""30 authenticated learners, real HTTP/Celery/sandbox. Credentials enter only through stdin."""
import asyncio
from collections import Counter
import csv
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import secrets
import sys
import time
from uuid import uuid4

import httpx
from sqlalchemy import func, or_, select

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/scripts")
from app.db import session
from app.models import Attempt, Submission
from smoke import C_SUM, CPP_SUM

USERS = 30
BASE = os.getenv("LOAD_BASE_URL", "http://api:8000")
PENDING = {"queued", "running", "retry_pending"}


def stats(values):
    values = sorted(values)
    if not values:
        return {"n": 0}
    return {"n": len(values), "min": round(values[0], 3), "median": round(values[math.ceil(len(values)*.5)-1], 3),
            "p95": round(values[math.ceil(len(values)*.95)-1], 3), "max": round(values[-1], 3)}


class LoadTest:
    def __init__(self):
        self.started = time.perf_counter()
        self.run_id = "perf_" + uuid4().hex[:10]
        self.directory = Path("/results")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.users, self.clients, self.enrollments = [], [], []
        self.requests, self.jobs, self.samples, self.bursts, self.anomalies = [], [], [], [], []
        self.sql_jobs, self.phases = {}, []
        self.course_id = None
        self.title = "Performance 30 users " + self.run_id
        self.stop = asyncio.Event()
        self.password = secrets.token_urlsafe(32)
        self.credentials = json.load(sys.stdin)
        self.admin = self.client()
        self.summary = {"run_id": self.run_id, "started_utc": datetime.now(timezone.utc).isoformat(),
                        "users": USERS, "base_url": BASE, "provider": "custom", "test_cases": 5,
                        "poll_interval_seconds": 1, "sql_sample_interval_seconds": .25,
                        "cleanup": {}, "status": "running"}

    def client(self):
        return httpx.AsyncClient(base_url=BASE, timeout=90,
                                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5))

    async def request(self, client, method, url, label, user=-1, **kwargs):
        started = time.perf_counter()
        record = {"label": label, "user": user, "method": method, "start_s": round(started-self.started, 6)}
        try:
            response = await client.request(method, url, **kwargs)
            record.update(status=response.status_code, latency_ms=round((time.perf_counter()-started)*1000, 3))
            if response.status_code >= 400:
                try:
                    detail = response.json().get("detail", "")
                    record["detail"] = detail if isinstance(detail, str) else "validation_error"
                except ValueError:
                    record["detail"] = "non_json_error"
            if response.status_code >= 500:
                self.anomalies.append({"type": "http_5xx", **record})
            return response
        except httpx.HTTPError as exc:
            record.update(status=0, latency_ms=round((time.perf_counter()-started)*1000, 3), detail=type(exc).__name__)
            self.anomalies.append({"type": "transport_error", **record})
            return None
        finally:
            self.requests.append(record)

    async def required(self, client, method, url, label, expected=200, **kwargs):
        response = await self.request(client, method, url, label, **kwargs)
        if response is None or response.status_code != expected:
            raise RuntimeError(f"{label}: expected HTTP {expected}, got {response.status_code if response else 'transport error'}")
        return response.json()

    async def burst(self, label, operations):
        gate = asyncio.Event()
        ready = 0
        launch = []

        async def operation(call):
            nonlocal ready
            ready += 1
            await gate.wait()
            launch.append(time.perf_counter())
            return await call()

        tasks = [asyncio.create_task(operation(call)) for call in operations]
        while ready < len(tasks):
            await asyncio.sleep(0)
        gate.set()
        results = await asyncio.gather(*tasks)
        self.bursts.append({"label": label, "requests": len(tasks),
                            "launch_span_ms": round((max(launch)-min(launch))*1000, 3)})
        return results

    async def setup(self):
        auth = await self.required(self.admin, "POST", "/auth/login", "setup_admin_login", json=self.credentials)
        self.credentials.clear()
        self.admin.headers["Authorization"] = "Bearer " + auth["access_token"]
        await self.required(self.admin, "GET", "/health/ready", "preflight")
        for index in range(USERS):
            user = await self.required(self.admin, "POST", "/admin/users", "setup_create_user", expected=201,
                json={"username": f"{self.run_id}_{index:02d}", "password": self.password, "role": "student"})
            self.users.append(user)
            self.clients.append(self.client())
        print("SETUP: 30 isolated student accounts created", flush=True)
        course = await self.required(self.admin, "POST", "/courses", "setup_course", expected=201,
                                     json={"title": self.title, "is_public": False})
        self.course_id = course["id"]
        for user in self.users:
            await self.required(self.admin, "POST", f"/courses/{self.course_id}/members", "setup_member", expected=201,
                                json={"user_id": user["id"]})
        lesson = await self.required(self.admin, "POST", f"/author/courses/{self.course_id}/lessons", "setup_lesson", expected=201,
                                    json={"title": "Concurrent sum", "body_markdown": "Read two integers and print their sum."})
        await self.required(self.admin, "POST", f"/author/lesson-versions/{lesson['id']}/publish", "setup_publish_lesson", json={"edit_revision": 1})
        cases = [{"input": "2 3\n", "expected": "5\n", "public": True},
                 {"input": "-7 -8\n", "expected": "-15\n", "public": False},
                 {"input": "0 0\n", "expected": "0\n", "public": False},
                 {"input": "1000000000 -1000000000\n", "expected": "0\n", "public": False},
                 {"input": "500000000 500000000\n", "expected": "1000000000\n", "public": False}]
        problem = await self.required(self.admin, "POST", f"/author/courses/{self.course_id}/problems", "setup_problem", expected=201,
            json={"title": "Sum C/C++", "statement": "Read a and b, print their sum.", "provider": "custom",
                  "languages": ["c17", "cpp17"], "cases": cases, "reference_solutions": {"c17": C_SUM, "cpp17": CPP_SUM}})
        self.problem_id = problem["id"]
        validation = await self.required(self.admin, "POST", f"/author/problem-versions/{self.problem_id}/validate", "setup_validate", expected=202, json={"edit_revision": 1})
        deadline = time.monotonic()+400
        while time.monotonic()<deadline:
            result = await self.required(self.admin, "GET", f"/author/validations/{validation['id']}", "setup_validation_poll")
            if result["state"] == "system_error":
                raise RuntimeError("Reference validation infrastructure failed")
            if result["state"] == "completed":
                if not result["valid"]:
                    raise RuntimeError("Reference solutions did not pass")
                break
            await asyncio.sleep(1)
        else:
            raise RuntimeError("Reference validation timed out")
        await self.required(self.admin, "POST", f"/author/problem-versions/{self.problem_id}/publish", "setup_publish_problem", json={"edit_revision": 1})
        path = await self.required(self.admin, "POST", f"/author/courses/{self.course_id}/paths", "setup_path", expected=201,
            json={"title": "Same path for 30 learners", "languages": ["c17", "cpp17"], "sequential": True, "steps": [
                {"key": "read", "title": "Read", "kind": "reading", "lesson_version_id": lesson["id"]},
                {"key": "sum", "title": "Sum", "kind": "exercise", "problem_version_id": self.problem_id}]})
        self.path_id = path["path_id"]
        await self.required(self.admin, "POST", f"/author/path-versions/{path['id']}/publish", "setup_publish_path", json={"edit_revision": 1})
        print("SETUP: one private class/path, C17/C++17 reference solutions validated on 5 test cases", flush=True)

    async def access(self):
        async def login(index):
            client = self.clients[index]
            response = await self.required(client, "POST", "/auth/login", "login_30", user=index,
                json={"username": self.users[index]["username"], "password": self.password})
            client.headers["Authorization"] = "Bearer " + response["access_token"]
        await self.burst("login_30", [lambda i=i: login(i) for i in range(USERS)])
        for label, url in (("home_30", "/"), ("classes_30", "/courses?status=active"),
                           ("same_class_30", f"/courses/{self.course_id}/learning")):
            results = await self.burst(label, [lambda i=i: self.request(self.clients[i], "GET", url, label, i) for i in range(USERS)])
            if any(r is None or r.status_code != 200 for r in results):
                raise RuntimeError(f"{label} failed")
        self.enrollments = await self.burst("enroll_same_path_30", [
            lambda i=i: self.required(self.clients[i], "POST", f"/paths/{self.path_id}/enroll", "enroll_same_path_30", user=i)
            for i in range(USERS)])
        for label, suffix in (("read_same_material_30", ""), ("complete_material_30", "/complete")):
            results = await self.burst(label, [
                lambda i=i: self.request(self.clients[i], "POST" if suffix else "GET",
                    f"/enrollments/{self.enrollments[i]['id']}/steps/{self.enrollments[i]['steps'][0]['id']}"+suffix, label, i)
                for i in range(USERS)])
            if any(r is None or r.status_code != 200 for r in results):
                raise RuntimeError(f"{label} failed")
        print("ACCESS: 30 concurrent logins, same class/path, enrollment and required reading completed", flush=True)

    def snapshot(self):
        with session() as db:
            users = [u["id"] for u in self.users]
            rows = db.execute(select(Attempt, Submission.created_at).join(Submission, Attempt.submission_id == Submission.id)
                              .where(Submission.owner_id.in_(users))).all()
            states = Counter()
            for attempt, created in rows:
                states[attempt.state] += 1
                row = self.sql_jobs.setdefault(attempt.submission_id, {"submission_id": attempt.submission_id,
                    "created_utc": created.isoformat(), "claimed_utc": None, "max_retries": 0})
                row["state"], row["verdict"], row["score"] = attempt.state, attempt.verdict, attempt.score
                row["max_retries"] = max(row["max_retries"], attempt.retries)
                row["error_code"] = attempt.error_code
                if attempt.lease_until and row["claimed_utc"] is None:
                    row["claimed_utc"] = (attempt.lease_until-timedelta(seconds=180)).isoformat()
                    row["queue_seconds"] = max(0, (attempt.lease_until-timedelta(seconds=180)-created).total_seconds())
                if attempt.finished_at:
                    row["finished_utc"] = attempt.finished_at.isoformat()
                    row["server_total_seconds"] = (attempt.finished_at-created).total_seconds()
                    if row["claimed_utc"]:
                        row["processing_seconds"] = (attempt.finished_at-datetime.fromisoformat(row["claimed_utc"])).total_seconds()
            external_pending = db.scalar(select(func.count()).select_from(Attempt).join(
                Submission, Attempt.submission_id == Submission.id).where(
                Attempt.state.in_(PENDING), or_(Submission.owner_id.not_in(users), Submission.owner_id.is_(None))))
            return {"at_s": round(time.perf_counter()-self.started, 3), **dict(states),
                    "own_pending": sum(states[s] for s in PENDING),
                    "external_pending": external_pending}

    async def sample(self):
        while not self.stop.is_set():
            try:
                self.samples.append(await asyncio.to_thread(self.snapshot))
            except Exception as exc:
                self.anomalies.append({"type": "sampler_error", "category": type(exc).__name__})
            await asyncio.sleep(.25)

    async def probe(self):
        while not self.stop.is_set():
            await self.request(self.clients[0], "GET", "/my/learning", "learning_probe_under_load", 0)
            await asyncio.sleep(1)

    def make_job(self, phase, index, mode, wrong=False):
        language = "c17" if index%2 == 0 else "cpp17"
        return {"phase": phase, "user": index, "mode": mode, "language": language, "wrong_source": wrong,
                "key": str(uuid4()), "expected_verdict": "EXECUTED" if mode == "run" else "WRONG_ANSWER" if wrong else "ACCEPTED",
                "expected_output": str(index*6), "http_attempts": [], "states": [], "submitted_s": None}

    async def admit(self, job, wave):
        index, mode = job["user"], job["mode"]
        data = {"problem_version_id": self.problem_id, "language": job["language"],
                "source": "int main(void){return 0;}" if job["wrong_source"] else C_SUM if job["language"] == "c17" else CPP_SUM,
                "enrollment_id": self.enrollments[index]["id"], "path_step_id": self.enrollments[index]["steps"][1]["id"]}
        if mode == "run":
            data["input"] = f"{index*7} {-index}\n"
        if job["submitted_s"] is None:
            job["submitted_s"] = time.perf_counter()-self.started
        response = await self.request(self.clients[index], "POST", "/runs" if mode == "run" else "/submissions",
            f"{job['phase']}_admission_wave_{wave}", index, json=data, headers={"Idempotency-Key": job["key"]})
        job["http_attempts"].append(response.status_code if response else 0)
        if response is not None and response.status_code == 202:
            row = response.json()
            job.update(submission_id=row["id"], accepted_s=time.perf_counter()-self.started)
            job["states"].append({"state": row["state"], "at_s": round(time.perf_counter()-self.started, 3)})
        elif response is None or response.status_code != 429:
            self.anomalies.append({"type": "admission_failure", "phase": job["phase"], "user": index,
                                   "status": response.status_code if response else 0})

    async def poll(self, job):
        deadline = time.monotonic()+600
        while time.monotonic()<deadline:
            response = await self.request(self.clients[job["user"]], "GET", f"/submissions/{job['submission_id']}",
                                          "result_poll", job["user"])
            if response is not None and response.status_code == 200:
                row = response.json()
                if not job["states"] or job["states"][-1]["state"] != row["state"]:
                    job["states"].append({"state": row["state"], "at_s": round(time.perf_counter()-self.started, 3)})
                if row["state"] not in PENDING:
                    job.update(final_state=row["state"], verdict=row["verdict"], score=row["score"],
                               completion_s=time.perf_counter()-self.started)
                    job["accepted_to_result_s"] = round(job["completion_s"]-job["accepted_s"], 3)
                    job["user_wait_s"] = round(job["completion_s"]-job["submitted_s"], 3)
                    if row["state"] != "completed" or row["verdict"] != job["expected_verdict"]:
                        self.anomalies.append({"type": "verdict_mismatch", "phase": job["phase"], "user": job["user"],
                                               "expected": job["expected_verdict"], "actual": row["verdict"], "state": row["state"]})
                    expected_score = None if job["mode"] == "run" else 0 if job["wrong_source"] else 100
                    if row["score"] != expected_score:
                        self.anomalies.append({"type": "score_mismatch", "user": job["user"]})
                    cases = (row.get("result") or {}).get("cases", [])
                    if job["mode"] == "run":
                        output = cases[0].get("stdout", "").strip() if cases else None
                        job["actual_output"] = output
                        if output != job["expected_output"]:
                            self.anomalies.append({"type": "output_mismatch", "user": job["user"], "expected": job["expected_output"], "actual": output})
                    elif any(set(case)&{"stdout","stderr","input","expected"} for case in cases[1:]):
                        self.anomalies.append({"type": "hidden_case_leak", "user": job["user"]})
                    return
            await asyncio.sleep(1)
        job["final_state"] = "poll_timeout"
        self.anomalies.append({"type": "unfinished_after_600s", "user": job["user"], "phase": job["phase"]})

    async def phase(self, name, jobs):
        self.jobs.extend(jobs)
        phase = {"name": name, "jobs": len(jobs), "start_s": time.perf_counter()-self.started}
        self.phases.append(phase)
        remaining = jobs
        for wave in range(1, 7):
            await self.burst(f"{name}_wave_{wave}", [lambda job=job: self.admit(job, wave) for job in remaining])
            admitted = [job for job in remaining if "submission_id" in job]
            rejected = [job for job in remaining if "submission_id" not in job and job["http_attempts"][-1] == 429]
            print(f"{name} wave {wave}: accepted={len(admitted)}, rejected429={len(rejected)}", flush=True)
            await asyncio.gather(*(self.poll(job) for job in admitted))
            remaining = rejected
            if not remaining:
                break
        for job in remaining:
            self.anomalies.append({"type": "retry_waves_exhausted", "user": job["user"], "phase": name})
        phase["duration_seconds"] = round(time.perf_counter()-self.started-phase["start_s"], 3)
        self.samples.append(await asyncio.to_thread(self.snapshot))
        print(f"{name}: drained in {phase['duration_seconds']}s", flush=True)

    async def verify_progress(self, label):
        progress = await self.burst(label, [lambda i=i: self.required(self.clients[i], "GET",
            f"/enrollments/{self.enrollments[i]['id']}", label, user=i) for i in range(USERS)])
        for index, row in enumerate(progress):
            if row["progress"] != 100 or row["score"] != 100 or not row["complete"]:
                self.anomalies.append({"type": "progress_mismatch", "user": index,
                                       "progress": row["progress"], "score": row["score"]})
        return [{"user": i, "progress": row["progress"], "score": row["score"],
                 "completion_seconds": row["completion_seconds"]} for i, row in enumerate(progress)]

    async def cleanup(self):
        if self.course_id:
            response = await self.request(self.admin, "DELETE", f"/courses/{self.course_id}", "cleanup_class",
                                          json={"confirmation_title": self.title})
            self.summary["cleanup"]["class_deleted"] = response is not None and response.status_code == 200
        disabled = 0
        for user in self.users:
            response = await self.request(self.admin, "PATCH", f"/admin/users/{user['id']}", "cleanup_disable_account",
                                          json={"is_active": False})
            disabled += response is not None and response.status_code == 200
        self.summary["cleanup"]["test_accounts_disabled"] = disabled
        # Accounts/audit remain for traceability; never delete pre-existing accounts or classes.
        for client in self.clients:
            await client.aclose()
        await self.admin.post("/auth/logout")
        await self.admin.aclose()

    def save(self):
        self.summary["finished_utc"] = datetime.now(timezone.utc).isoformat()
        self.summary["duration_seconds"] = round(time.perf_counter()-self.started, 3)
        self.summary["anomalies"] = self.anomalies
        self.summary["request_groups"] = {
            label: {"http": dict(Counter(str(r["status"]) for r in self.requests if r["label"] == label)),
                    "latency_ms": stats([r["latency_ms"] for r in self.requests if r["label"] == label])}
            for label in sorted({r["label"] for r in self.requests})}
        self.summary["queue_peaks"] = {key: max((sample.get(key, 0) for sample in self.samples), default=0)
                                       for key in ("queued", "running", "retry_pending", "own_pending", "external_pending")}
        for phase in self.phases:
            rows = [job for job in self.jobs if job["phase"] == phase["name"]]
            phase["initial_http"] = dict(Counter(str(job["http_attempts"][0]) for job in rows))
            phase["final_states"] = dict(Counter(job.get("final_state", "not_admitted") for job in rows))
            phase["verdicts"] = dict(Counter(str(job.get("verdict")) for job in rows))
            phase["accepted_to_result_seconds"] = stats([job["accepted_to_result_s"] for job in rows if "completion_s" in job])
            phase["user_wait_seconds"] = stats([job["user_wait_s"] for job in rows if "completion_s" in job])
            sql = [self.sql_jobs[job["submission_id"]] for job in rows if job.get("submission_id") in self.sql_jobs]
            phase["queue_seconds"] = stats([row["queue_seconds"] for row in sql if "queue_seconds" in row])
            phase["processing_seconds"] = stats([row["processing_seconds"] for row in sql if "processing_seconds" in row])
            phase["retries"] = sum(row["max_retries"] for row in sql)
        self.summary["phases"] = self.phases
        raw = {"summary": self.summary, "bursts": self.bursts, "requests": self.requests,
               "jobs": [{k:v for k,v in job.items() if k != "key"} for job in self.jobs],
               "sql_jobs": list(self.sql_jobs.values()), "samples": self.samples}
        (self.directory/"results.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")
        for name, rows in (("requests", self.requests), ("queue", self.samples),
                           ("jobs", [{k:v for k,v in row.items() if k not in ("key","states","http_attempts")} for row in self.jobs])):
            with (self.directory/f"{name}.csv").open("w", newline="", encoding="utf-8") as file:
                fields = sorted(set().union(*(row.keys() for row in rows))) if rows else ["empty"]
                writer = csv.DictWriter(file, fieldnames=fields)
                writer.writeheader(); writer.writerows(rows)
        print(json.dumps({"status": self.summary["status"], "anomalies": len(self.anomalies),
                          "cleanup": self.summary["cleanup"], "results": "/results/results.json"}), flush=True)

    async def run(self):
        tasks = []
        try:
            await self.setup()
            await self.access()
            tasks = [asyncio.create_task(self.sample()), asyncio.create_task(self.probe())]
            await self.phase("run_30", [self.make_job("run_30", i, "run") for i in range(USERS)])
            run_progress = await self.burst("progress_after_run_30", [lambda i=i: self.required(self.clients[i], "GET",
                f"/enrollments/{self.enrollments[i]['id']}", "progress_after_run_30", user=i) for i in range(USERS)])
            self.summary["run_did_not_complete_exercise"] = all(row["progress"] == 50 and row["score"] == 0 and not row["complete"] for row in run_progress)
            if not self.summary["run_did_not_complete_exercise"]:
                self.anomalies.append({"type": "run_incorrectly_changed_progress"})
            await self.phase("submit_30", [self.make_job("submit_30", i, "judge") for i in range(USERS)])
            self.summary["progress_after_submit"] = await self.verify_progress("progress_after_submit_30")
            mixed = [self.make_job("mixed_60", i, mode, wrong=(mode == "judge" and i%3 == 0))
                     for i in range(USERS) for mode in ("run", "judge")]
            await self.phase("mixed_60", mixed)
            self.summary["progress_after_mixed"] = await self.verify_progress("progress_after_mixed_30")
            if self.summary["progress_after_submit"] != self.summary["progress_after_mixed"]:
                self.anomalies.append({"type": "repeat_submission_changed_final_progress_or_time"})
            leaderboard = await self.required(self.admin, "GET", f"/courses/{self.course_id}/leaderboard", "final_leaderboard")
            self.summary["leaderboard_students"] = len(leaderboard["rows"])
            if len(leaderboard["rows"]) != USERS or any(row["score"] != 100 for row in leaderboard["rows"]):
                self.anomalies.append({"type": "leaderboard_mismatch"})
            self.summary["status"] = "completed"
        except Exception as exc:
            self.summary["status"] = "failed"
            self.anomalies.append({"type": "harness_or_setup_error", "category": type(exc).__name__, "message": str(exc)[:250]})
            print(f"TEST ERROR: {type(exc).__name__}: {exc}", flush=True)
        finally:
            self.stop.set()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            try:
                await self.cleanup()
            except Exception as exc:
                self.summary["cleanup"]["error"] = type(exc).__name__
            self.save()


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        assert stats([5, 1, 2, 4, 3]) == {"n": 5, "min": 1, "median": 3, "p95": 5, "max": 5}
        assert stats([]) == {"n": 0}
        print("PASS nearest-rank latency summaries and empty samples")
    else:
        asyncio.run(LoadTest().run())
