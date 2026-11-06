"""Detailed benchmark using the existing load generator, plus isolated runner controls."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/scripts")
import httpx
from app.contracts import Case, JudgeRequest, Limits
from smoke import C_SUM, CPP_SUM

spec = importlib.util.spec_from_file_location("load_concurrent", "/loadtest.py")
load = importlib.util.module_from_spec(spec)
spec.loader.exec_module(load)


async def calibrate(label):
    rows = []
    cases = [Case(id=str(i), input=value, expected=expected, public=i == 0) for i, (value, expected) in enumerate([
        ("2 3\n", "5\n"), ("-7 -8\n", "-15\n"), ("0 0\n", "0\n"),
        ("1000000000 -1000000000\n", "0\n"), ("500000000 500000000\n", "1000000000\n")])]
    async with httpx.AsyncClient(base_url=os.environ["RUNNER_URL"], timeout=150) as client:
        for repeat in range(2):
            for language, source in (("c17", C_SUM), ("cpp17", CPP_SUM)):
                for mode in ("run", "judge"):
                    request = JudgeRequest(attempt_id=uuid4(), language=language, source=source, mode=mode,
                        limits=Limits(), cases=cases if mode == "judge" else [Case(id="custom-input", input="123 456\n", public=True)])
                    start_ns, start = time.time_ns(), time.perf_counter()
                    response = await client.post("/judge", json=request.model_dump(mode="json"),
                        headers={"X-Runner-Token": os.environ["RUNNER_TOKEN"]})
                    duration = (time.perf_counter()-start)*1000
                    assert response.status_code == 200, f"Calibration infrastructure HTTP {response.status_code}"
                    result = response.json()
                    assert result["verdict"] == ("EXECUTED" if mode == "run" else "ACCEPTED"), "Calibration verdict mismatch"
                    assert mode != "run" or result["cases"][0]["stdout"].strip() == "579", "Calibration output mismatch"
                    rows.append({"attempt_id": str(request.attempt_id), "language": language, "mode": mode,
                                 "repeat": repeat, "start_ns": start_ns, "duration_ms": round(duration, 3)})
                    print(f"CALIBRATION {label} {language} {mode}: {duration:.1f} ms", flush=True)
    Path(f"/results/calibration-{label}.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")


class DetailedLoad(load.LoadTest):
    def __init__(self):
        super().__init__()
        self.polling, self.submission_attempts = {}, {}
        self.summary.update(profiling=True, clock_origin_ns=time.time_ns()-round((time.perf_counter()-self.started)*1e9),
                            poll_starts="Immediately after each accepted response, independently of other requests")

    async def request(self, client, method, url, label, user=-1, **kwargs):
        response = await super().request(client, method, url, label, user, **kwargs)
        if method == "POST" and url in ("/runs", "/submissions") and response is not None and response.status_code == 202:
            row = response.json()
            self.submission_attempts[row["id"]] = row["attempt_id"]
        return response

    async def admit(self, job, wave):
        await super().admit(job, wave)
        if "submission_id" in job:
            job["attempt_id"] = self.submission_attempts[job["submission_id"]]
            self.polling[job["key"]] = asyncio.create_task(self.poll(job))

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
            await asyncio.gather(*(self.polling[job["key"]] for job in admitted))
            remaining = rejected
            if not remaining:
                break
        for job in remaining:
            self.anomalies.append({"type": "retry_waves_exhausted", "user": job["user"], "phase": name})
        phase["duration_seconds"] = round(time.perf_counter()-self.started-phase["start_s"], 3)
        self.samples.append(await asyncio.to_thread(self.snapshot))
        print(f"{name}: drained in {phase['duration_seconds']}s", flush=True)

    async def run(self):
        tasks = []
        try:
            await self.setup()
            await self.access()
            tasks = [asyncio.create_task(self.sample()), asyncio.create_task(self.probe())]
            for index, language in ((0, "c17"), (1, "cpp17")):
                for mode in ("run", "judge"):
                    name = f"single_{language}_{mode}"
                    await self.phase(name, [self.make_job(name, index, mode)])
            await self.phase("run_30", [self.make_job("run_30", i, "run") for i in range(load.USERS)])
            await self.phase("submit_30", [self.make_job("submit_30", i, "judge") for i in range(load.USERS)])
            self.summary["progress_after_submit"] = await self.verify_progress("progress_after_submit_30")
            self.summary["status"] = "completed"
        except Exception as exc:
            self.summary["status"] = "failed"
            self.anomalies.append({"type": "harness_or_setup_error", "category": type(exc).__name__, "message": str(exc)[:250]})
            print(f"TEST ERROR: {type(exc).__name__}: {exc}", flush=True)
        finally:
            self.stop.set()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.gather(*self.polling.values(), return_exceptions=True)
            try:
                await self.cleanup()
            except Exception as exc:
                self.summary["cleanup"]["error"] = type(exc).__name__
            self.save()


if __name__ == "__main__":
    if "--calibrate" in sys.argv:
        asyncio.run(calibrate(sys.argv[-1]))
    else:
        asyncio.run(DetailedLoad().run())
