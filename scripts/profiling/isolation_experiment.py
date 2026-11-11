"""Controlled comparison of two runners: S0 (one container start per phase) vs S1 (one start for all cases).

Both runners run side by side, so trials are interleaved in a random order without restarts. Talks to the
runners only (no database). Run inside the Compose network, with nothing else loading the Docker host:
  docker compose run --rm --no-deps -v ./scripts/profiling/isolation_experiment.py:/tmp/x.py:ro \
      -v <out dir>:/results api python /tmp/x.py --reps 10 --out /results
Environment: RUNNER_TOKEN, S0_URL (default http://runner-s0:8001), S1_URL (default http://runner:8001).
Stop every other container on the Docker host first: /proc/stat counts the whole host/VM.
Analyse with scripts/profiling/analyze_isolation.py <out dir> [fixed idle baseline in CPUs].

Experiment A (solo): for every variant and N in {1, 2, 5, 10} test cases, REPS trials of 5 sequential jobs.
Experiment B (parallel): for every variant, REPS trials of 12 jobs with N=5 at 6 concurrent requests.
CPU is the busy time of the whole Docker host/VM from /proc/stat minus its idle background. The idle rate drifts
(Docker Desktop VM), so it is sampled before, every IDLE_EVERY trials and after, and interpolated per trial.
"""
import argparse
import csv
import json
import os
import random
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import httpx

SOURCE = '#include <stdio.h>\nint main(void){long long a,b;if(scanf("%lld %lld",&a,&b)!=2)return 1;printf("%lld\\n",a+b);return 0;}'
CASES_N = (1, 2, 5, 10)
SETTLE = 2.0  # seconds after a trial: S1 removes containers in the background, and that work must be counted.
IDLE_EVERY, IDLE_SECONDS = 8, 10.0
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
       11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 19: 2.093, 24: 2.064, 29: 2.045}


def busy_ticks():
    with open("/proc/stat") as stat:
        fields = [int(value) for value in stat.readline().split()[1:]]
    return sum(fields) - fields[3] - fields[4]


def idle_rate(seconds, quiet=3.0):
    """(moment, busy CPU-seconds per second) while nothing is submitted, after letting earlier work finish."""
    time.sleep(quiet)
    start, began = busy_ticks(), time.monotonic()
    time.sleep(seconds)
    window = time.monotonic() - began
    return began + window / 2, (busy_ticks() - start) / os.sysconf("SC_CLK_TCK") / window


def job(url, token, cases):
    body = {"attempt_id": str(uuid4()), "language": "c17", "source": SOURCE, "mode": "judge", "limits": {},
            "cases": [{"id": f"c{i}", "input": f"{i} {i}\n", "expected": str(2 * i)} for i in range(cases)]}
    started = time.monotonic()
    response = httpx.post(f"{url}/judge", json=body, headers={"X-Runner-Token": token}, timeout=300)
    seconds = time.monotonic() - started
    verdict = response.json().get("verdict") if response.status_code == 200 else f"HTTP {response.status_code}"
    return seconds, verdict


def trial(url, token, cases, jobs, parallel):
    """Returns job results, the jobs' wall time, the busy CPU-seconds of the window and the window itself."""
    hz = os.sysconf("SC_CLK_TCK")
    start, began = busy_ticks(), time.monotonic()
    with ThreadPoolExecutor(parallel) as pool:
        results = list(pool.map(lambda _: job(url, token, cases), range(jobs)))
    wall = time.monotonic() - began
    time.sleep(SETTLE)
    window = time.monotonic() - began
    return results, wall, (busy_ticks() - start) / hz, window, began + window / 2


def interpolate(samples, moment):
    """Idle busy-CPU rate at a moment, linear between the nearest idle samples."""
    before = max((s for s in samples if s[0] <= moment), default=samples[0])
    after = min((s for s in samples if s[0] >= moment), default=samples[-1])
    if after[0] == before[0]:
        return before[1]
    return before[1] + (after[1] - before[1]) * (moment - before[0]) / (after[0] - before[0])


def mean_ci(values):
    mean = statistics.fmean(values)
    if len(values) < 2:
        return mean, float("nan")
    t = T95.get(len(values) - 1, 1.96)
    return mean, t * statistics.stdev(values) / len(values) ** 0.5


def bootstrap_median_ci(values, rng, rounds=2000):
    medians = sorted(statistics.median(rng.choices(values, k=len(values))) for _ in range(rounds))
    return medians[int(rounds * 0.025)], medians[int(rounds * 0.975)]


def percentile(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))]


def fit(points):
    xs, ys = zip(*points)
    slope, intercept = statistics.linear_regression(xs, ys)
    mean_y = statistics.fmean(ys)
    residual = sum((y - (intercept + slope * x)) ** 2 for x, y in points)
    total = sum((y - mean_y) ** 2 for y in ys)
    return {"intercept": intercept, "slope": slope, "r2": 1 - residual / total if total else float("nan")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reps", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20261111)
    parser.add_argument("--baseline-seconds", type=float, default=60)
    parser.add_argument("--out", default="/results")
    args = parser.parse_args()
    token = os.environ["RUNNER_TOKEN"]
    urls = {"S0": os.getenv("S0_URL", "http://runner-s0:8001"), "S1": os.getenv("S1_URL", "http://runner:8001")}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    for variant, url in urls.items():  # Warm-up, discarded: first compilations and image pages.
        for cases in CASES_N:
            job(url, token, cases)
    idle = [idle_rate(args.baseline_seconds, quiet=10.0)]
    print(f"idle baseline before: {idle[0][1]:.3f} busy CPUs", flush=True)

    plan = [("A", v, n, r, 5, 1) for v in urls for n in CASES_N for r in range(args.reps)]
    plan_b = [("B", v, 5, r, 12, 6) for v in urls for r in range(args.reps)]
    rng.shuffle(plan)
    rng.shuffle(plan_b)
    job_rows, trial_rows = [], []
    for index, (experiment, variant, cases, rep, jobs, parallel) in enumerate(plan + plan_b, 1):
        results, wall, gross, window, moment = trial(urls[variant], token, cases, jobs, parallel)
        trial_rows.append({"experiment": experiment, "variant": variant, "cases": cases, "rep": rep, "jobs": jobs,
                           "parallel": parallel, "wall": wall, "gross_cpu": gross, "window": window,
                           "moment": moment, "ok": sum(v == "ACCEPTED" for _, v in results)})
        job_rows += [{"experiment": experiment, "variant": variant, "cases": cases, "rep": rep, "latency": s,
                      "verdict": v, "ok": v == "ACCEPTED"} for s, v in results]
        print(f"{experiment} {index}/{len(plan) + len(plan_b)} {variant} N={cases} rep={rep} "
              f"gross_cpu/job={gross / jobs:.2f} throughput={jobs / wall:.2f}/s", flush=True)
        if index % IDLE_EVERY == 0:
            idle.append(idle_rate(IDLE_SECONDS))
    idle.append(idle_rate(args.baseline_seconds))
    print(f"idle baseline after: {idle[-1][1]:.3f} busy CPUs", flush=True)
    for row in trial_rows:
        row["idle_rate"] = interpolate(idle, row["moment"])
        row["cpu_per_job"] = (row["gross_cpu"] - row["idle_rate"] * row["window"]) / row["jobs"]

    for name, rows in (("jobs.csv", job_rows), ("trials.csv", trial_rows)):
        with open(out / name, "w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    summary = {"reps": args.reps, "seed": args.seed, "settle_seconds": SETTLE,
               "idle_samples": len(idle), "idle_rate_min_max": [min(r for _, r in idle), max(r for _, r in idle)],
               "idle": [{"moment": m, "busy_cpus": r} for m, r in idle],
               "failed_jobs": sum(not row["ok"] for row in job_rows),
               "failed_verdicts": sorted({f"{r['variant']}/N={r['cases']}: {r['verdict']}" for r in job_rows if not r["ok"]}), "A": {}, "B": {}, "model": {}}
    for variant in urls:
        points = []
        for cases in CASES_N:
            latencies = [r["latency"] for r in job_rows if r["experiment"] == "A" and r["variant"] == variant
                         and r["cases"] == cases]
            cpus = [r["cpu_per_job"] for r in trial_rows if r["experiment"] == "A" and r["variant"] == variant
                    and r["cases"] == cases]
            cpu_mean, cpu_half = mean_ci(cpus)
            summary["A"][f"{variant}/N={cases}"] = {
                "latency_median": statistics.median(latencies),
                "latency_median_ci95": bootstrap_median_ci(latencies, rng),
                "latency_p95": percentile(latencies, 0.95), "latency_n": len(latencies),
                "cpu_mean": cpu_mean, "cpu_ci95_half": cpu_half, "cpu_trials": len(cpus)}
            points += [(cases, cpu) for cpu in cpus]
        summary["model"][variant] = fit(points)
        trials_b = [r for r in trial_rows if r["experiment"] == "B" and r["variant"] == variant]
        latencies_b = [r["latency"] for r in job_rows if r["experiment"] == "B" and r["variant"] == variant]
        throughput = [r["jobs"] / r["wall"] for r in trials_b]
        cpu_b = [r["cpu_per_job"] for r in trials_b]
        summary["B"][variant] = {
            "throughput_mean_ci95": mean_ci(throughput), "cpu_mean_ci95": mean_ci(cpu_b),
            "latency_median": statistics.median(latencies_b),
            "latency_median_ci95": bootstrap_median_ci(latencies_b, rng),
            "latency_p95": percentile(latencies_b, 0.95), "latency_n": len(latencies_b)}
    summary["model"]["extra_cpu_per_case_S0_minus_S1"] = (
        summary["model"]["S0"]["slope"] - summary["model"]["S1"]["slope"])
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
