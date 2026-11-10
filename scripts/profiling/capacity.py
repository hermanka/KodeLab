"""Measure judging capacity of a Docker host: CPU-seconds per job and throughput.

Talks to the runner only (no database, no accounts). Run inside the Compose network, for example:
  docker compose up -d --no-deps runner
  docker compose run --rm --no-deps -v ./scripts/profiling/capacity.py:/tmp/capacity.py:ro api python /tmp/capacity.py judge 24 6
Arguments: <judge|run> <jobs> <parallel> [c17|cpp17]. judge = compile + 5 cases (Submit), run = compile + 1 input (Run).
CPU comes from /proc/stat of the Docker host/VM, so stop other load while measuring.
"""
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import httpx

SOURCES = {
    "c17": '#include <stdio.h>\nint main(void){long long a,b;if(scanf("%lld %lld",&a,&b)!=2)return 1;printf("%lld\\n",a+b);return 0;}',
    "cpp17": '#include <iostream>\nint main(){long long a,b;if(!(std::cin>>a>>b))return 1;std::cout<<a+b<<"\\n";}',
}


def cpu_ticks():
    with open("/proc/stat") as stat:
        fields = [int(value) for value in stat.readline().split()[1:]]
    return sum(fields) - fields[3] - fields[4], fields[3] + fields[4]  # busy, idle+iowait


def job(mode, url, token, language):
    cases = ([{"id": f"c{i}", "input": f"{i} {i}\n", "expected": str(2 * i)} for i in range(5)]
             if mode == "judge" else [{"id": "c0", "input": "40 2\n", "public": True}])
    body = {"attempt_id": str(uuid4()), "language": language, "source": SOURCES[language], "mode": mode, "limits": {}, "cases": cases}
    started = time.monotonic()
    response = httpx.post(f"{url}/judge", json=body, headers={"X-Runner-Token": token}, timeout=300)
    response.raise_for_status()
    return time.monotonic() - started, response.json()["verdict"] in ("ACCEPTED", "EXECUTED")


def main():
    mode, jobs, parallel = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    language = sys.argv[4] if len(sys.argv) > 4 else "c17"
    assert mode in ("judge", "run") and jobs >= parallel >= 1
    url, token = os.getenv("RUNNER_URL", "http://runner:8001"), os.environ["RUNNER_TOKEN"]
    busy0, idle0 = cpu_ticks()
    started = time.monotonic()
    with ThreadPoolExecutor(parallel) as pool:
        results = list(pool.map(lambda _: job(mode, url, token, language), range(jobs)))
    wall = time.monotonic() - started
    busy1, idle1 = cpu_ticks()
    hz, cpus = os.sysconf("SC_CLK_TCK"), os.cpu_count()
    latency = sorted(seconds for seconds, _ in results)
    print(f"{mode} {language} jobs={jobs} parallel={parallel} ok={sum(ok for _, ok in results)}/{jobs} wall={wall:.1f}s "
          f"throughput={jobs / wall:.2f}/s latency_median={latency[len(latency) // 2]:.2f}s max={latency[-1]:.2f}s")
    busy, idle = busy1 - busy0, idle1 - idle0
    print(f"cpu_seconds_per_job={busy / hz / jobs:.2f} avg_busy_cpus={busy / (busy + idle) * cpus:.2f} of {cpus}")


if __name__ == "__main__":
    main()
