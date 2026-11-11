"""Turn isolation_experiment.py output (jobs.csv, trials.csv) into the paper's tables (Indonesian number format).

Usage: analyze_isolation.py <result dir> [fixed idle baseline in busy CPUs]. With the baseline argument it also
reports medians and Theil-Sen slopes, which tolerate trials disturbed by unrelated load on the Docker host.
"""
import csv
import random
import statistics
import sys
from pathlib import Path

directory = Path(sys.argv[1])
rng = random.Random(7)
jobs = list(csv.DictReader(open(directory / "jobs.csv")))
trials = list(csv.DictReader(open(directory / "trials.csv")))
for row in jobs:
    row["latency"], row["cases"] = float(row["latency"]), int(row["cases"])
for row in trials:
    row["cpu_per_job"], row["cases"] = float(row["cpu_per_job"]), int(row["cases"])
    row["throughput"] = int(row["jobs"]) / float(row["wall"])
CASES = sorted({row["cases"] for row in trials if row["experiment"] == "A"})
B = 4000


def boot(values, statistic):
    stats = sorted(statistic(rng.choices(values, k=len(values))) for _ in range(B))
    return stats[int(B * 0.025)], stats[int(B * 0.975)]


def boot_ratio(a, b, statistic):
    stats = sorted(statistic(rng.choices(a, k=len(a))) / statistic(rng.choices(b, k=len(b))) for _ in range(B))
    return stats[int(B * 0.025)], stats[int(B * 0.975)]


def pct(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def f(x, d=2):
    return f"{x:.{d}f}".replace(".", ",")


def sel(table, experiment, variant, cases=None):
    return [r for r in table if r["experiment"] == experiment and r["variant"] == variant
            and (cases is None or r["cases"] == cases)]


def fit(points):
    xs, ys = zip(*points)
    slope, intercept = statistics.linear_regression(xs, ys)
    mean = statistics.fmean(ys)
    ss_res = sum((y - intercept - slope * x) ** 2 for x, y in points)
    ss_tot = sum((y - mean) ** 2 for y in ys)
    return intercept, slope, 1 - ss_res / ss_tot


out = []
failed = [r for r in jobs if r["ok"] != "True"]
out.append(f"Pekerjaan: {len(jobs)}, gagal: {len(failed)} {sorted({(r['variant'], r['cases'], r['verdict']) for r in failed})}")

out.append("\n### Tabel A1. Latensi per pekerjaan (paralel 1), median [CI 95% bootstrap], p95\n")
out.append("| N | S0 median [CI] | S0 p95 | S1 median [CI] | S1 p95 | S0/S1 (median) [CI] |")
out.append("|---:|---|---:|---|---:|---|")
for n in CASES:
    a = [r["latency"] for r in sel(jobs, "A", "S0", n)]
    b = [r["latency"] for r in sel(jobs, "A", "S1", n)]
    ma, mb = statistics.median(a), statistics.median(b)
    la, ha = boot(a, statistics.median)
    lb, hb = boot(b, statistics.median)
    lr, hr = boot_ratio(a, b, statistics.median)
    out.append(f"| {n} | {f(ma)} [{f(la)}–{f(ha)}] s | {f(pct(a, .95))} s | {f(mb)} [{f(lb)}–{f(hb)}] s | "
               f"{f(pct(b, .95))} s | {f(ma / mb, 1)}× [{f(lr, 1)}–{f(hr, 1)}] |")

out.append("\n### Tabel A2. Biaya CPU per pekerjaan (detik-CPU, dikoreksi baseline idle), rerata ± CI 95%\n")
out.append("| N | S0 rerata [CI] | S1 rerata [CI] | S0/S1 [CI] |")
out.append("|---:|---|---|---|")
for n in CASES:
    a = [r["cpu_per_job"] for r in sel(trials, "A", "S0", n)]
    b = [r["cpu_per_job"] for r in sel(trials, "A", "S1", n)]
    la, ha = boot(a, statistics.fmean)
    lb, hb = boot(b, statistics.fmean)
    lr, hr = boot_ratio(a, b, statistics.fmean)
    out.append(f"| {n} | {f(statistics.fmean(a))} [{f(la)}–{f(ha)}] | {f(statistics.fmean(b))} [{f(lb)}–{f(hb)}] | "
               f"{f(statistics.fmean(a) / statistics.fmean(b), 1)}× [{f(lr, 1)}–{f(hr, 1)}] |")

out.append("\n### Tabel A3. Regresi linear terhadap N (per percobaan)\n")
out.append("| Ukuran | Varian | Intersep | Kemiringan per kasus [CI 95%] | R² |")
out.append("|---|---|---:|---|---:|")
slopes = {}
for label, table, key in (("Latensi (s)", jobs, "latency"), ("CPU (detik-CPU)", trials, "cpu_per_job")):
    for variant in ("S0", "S1"):
        rows = sel(table, "A", variant)
        intercept, slope, r2 = fit([(r["cases"], r[key]) for r in rows])
        by_n = {n: [r[key] for r in rows if r["cases"] == n] for n in CASES}
        boots = []
        for _ in range(B):
            sample = [(n, v) for n in CASES for v in rng.choices(by_n[n], k=len(by_n[n]))]
            boots.append(fit(sample)[1])
        boots.sort()
        slopes[(label, variant)] = (slope, boots)
        out.append(f"| {label} | {variant} | {f(intercept)} | {f(slope, 3)} [{f(boots[int(B*.025)], 3)}–{f(boots[int(B*.975)], 3)}] | {f(r2, 3)} |")
for label in ("Latensi (s)", "CPU (detik-CPU)"):
    s0, b0 = slopes[(label, "S0")]
    s1, b1 = slopes[(label, "S1")]
    diff = sorted(x - y for x, y in zip(b0, b1))
    out.append(f"\nSelisih kemiringan S0 − S1, {label}: {f(s0 - s1, 3)} per kasus [CI {f(diff[int(B*.025)], 3)}–{f(diff[int(B*.975)], 3)}]")

out.append("\n### Tabel B. 12 pekerjaan, N = 5, paralel 6\n")
out.append("| Ukuran | S0 | S1 | S1/S0 atau S0/S1 [CI] |")
out.append("|---|---|---|---|")
tb = {v: sel(trials, "B", v) for v in ("S0", "S1")}
jb = {v: [r["latency"] for r in sel(jobs, "B", v)] for v in ("S0", "S1")}
t0, t1 = [r["throughput"] for r in tb["S0"]], [r["throughput"] for r in tb["S1"]]
c0, c1 = [r["cpu_per_job"] for r in tb["S0"]], [r["cpu_per_job"] for r in tb["S1"]]
l, h = boot_ratio(t1, t0, statistics.fmean)
out.append(f"| Throughput (pekerjaan/s), rerata [CI] | {f(statistics.fmean(t0))} [{'–'.join(f(x) for x in boot(t0, statistics.fmean))}] | "
           f"{f(statistics.fmean(t1))} [{'–'.join(f(x) for x in boot(t1, statistics.fmean))}] | {f(statistics.fmean(t1)/statistics.fmean(t0), 1)}× [{f(l, 1)}–{f(h, 1)}] |")
l, h = boot_ratio(jb["S0"], jb["S1"], statistics.median)
out.append(f"| Latensi median [CI] | {f(statistics.median(jb['S0']))} [{'–'.join(f(x) for x in boot(jb['S0'], statistics.median))}] s | "
           f"{f(statistics.median(jb['S1']))} [{'–'.join(f(x) for x in boot(jb['S1'], statistics.median))}] s | {f(statistics.median(jb['S0'])/statistics.median(jb['S1']), 1)}× [{f(l, 1)}–{f(h, 1)}] |")
out.append(f"| Latensi p95 | {f(pct(jb['S0'], .95))} s | {f(pct(jb['S1'], .95))} s | |")
l, h = boot_ratio(c0, c1, statistics.fmean)
out.append(f"| CPU per pekerjaan, rerata [CI] | {f(statistics.fmean(c0))} [{'–'.join(f(x) for x in boot(c0, statistics.fmean))}] | "
           f"{f(statistics.fmean(c1))} [{'–'.join(f(x) for x in boot(c1, statistics.fmean))}] | {f(statistics.fmean(c0)/statistics.fmean(c1), 1)}× [{f(l, 1)}–{f(h, 1)}] |")
idle = [float(r["idle_rate"]) for r in trials]
out.append(f"\nBaseline idle terinterpolasi: {f(min(idle))}–{f(max(idle))} CPU sibuk.")
text = "\n".join(out)
(directory / "tabel.md").write_text(text, encoding="utf-8")
print(text)

# Robust CPU analysis: a constant idle baseline from the clean first/last idle samples (argv[2], CPUs) and
# medians instead of means, because idle samples in the middle of the run were hit by unrelated containers.
if len(sys.argv) > 2:
    base = float(sys.argv[2])
    for row in trials:
        row["cpu_robust"] = (float(row["gross_cpu"]) - base * float(row["window"])) / int(row["jobs"])
    out = [f"\n### Tabel A2-R. CPU per pekerjaan, median [CI 95% bootstrap], baseline tetap {f(base)} CPU\n",
           "| N | S0 median [CI] | S1 median [CI] | S0/S1 [CI] |", "|---:|---|---|---|"]
    points = {"S0": [], "S1": []}
    for n in CASES:
        a = [r["cpu_robust"] for r in sel(trials, "A", "S0", n)]
        b = [r["cpu_robust"] for r in sel(trials, "A", "S1", n)]
        points["S0"] += [(n, x) for x in a]
        points["S1"] += [(n, x) for x in b]
        la, ha = boot(a, statistics.median)
        lb, hb = boot(b, statistics.median)
        lr, hr = boot_ratio(a, b, statistics.median)
        out.append(f"| {n} | {f(statistics.median(a))} [{f(la)}–{f(ha)}] | {f(statistics.median(b))} [{f(lb)}–{f(hb)}] | "
                   f"{f(statistics.median(a) / statistics.median(b), 1)}× [{f(lr, 1)}–{f(hr, 1)}] |")
    # Theil–Sen slope (median of pairwise slopes): robust to the contaminated trials.
    def theil_sen(pts):
        slopes = sorted((y2 - y1) / (x2 - x1) for i, (x1, y1) in enumerate(pts) for x2, y2 in pts[i + 1:] if x2 != x1)
        return statistics.median(slopes)
    for v in ("S0", "S1"):
        boots = sorted(theil_sen([p for n in CASES for p in rng.choices([q for q in points[v] if q[0] == n], k=10)])
                       for _ in range(400))
        out.append(f"\nKemiringan Theil–Sen CPU {v}: {f(theil_sen(points[v]), 3)} detik-CPU per kasus "
                   f"[CI {f(boots[10], 3)}–{f(boots[389], 3)}]")
    a = [r["cpu_robust"] for r in sel(trials, "B", "S0")]
    b = [r["cpu_robust"] for r in sel(trials, "B", "S1")]
    lr, hr = boot_ratio(a, b, statistics.median)
    out.append(f"\nEksperimen B, CPU per pekerjaan median: S0 {f(statistics.median(a))} [{'–'.join(f(x) for x in boot(a, statistics.median))}], "
               f"S1 {f(statistics.median(b))} [{'–'.join(f(x) for x in boot(b, statistics.median))}], S0/S1 {f(statistics.median(a)/statistics.median(b), 1)}× [{f(lr, 1)}–{f(hr, 1)}]")
    robust = "\n".join(out)
    with open(directory / "tabel.md", "a", encoding="utf-8") as file:
        file.write("\n" + robust)
    print(robust)
