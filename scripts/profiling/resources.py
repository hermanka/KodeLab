"""Sample Docker Linux VM CPU and available memory without access to the Docker socket."""
import json
from pathlib import Path
import time

directory = Path("/results")
previous = None
with (directory/"resources.jsonl").open("a", buffering=1) as output:
    while not (directory/"monitor.stop").exists():
        cpu = [int(value) for value in Path("/proc/stat").read_text().splitlines()[0].split()[1:9]]
        total, idle = sum(cpu), cpu[3]+cpu[4]
        memory = {line.split(":")[0]: int(line.split()[1])*1024 for line in Path("/proc/meminfo").read_text().splitlines()}
        usage = None
        if previous and total > previous[0]:
            usage = 100*(1-(idle-previous[1])/(total-previous[0]))
        output.write(json.dumps({"at_ns": time.time_ns(), "vm_cpu_percent": usage,
            "vm_memory_total_bytes": memory["MemTotal"], "vm_memory_available_bytes": memory["MemAvailable"]})+"\n")
        previous = total, idle
        time.sleep(1)
