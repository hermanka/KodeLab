"""Which kernel check protects an in-container supervisor? An empirical matrix for the paper (Tabel 2, bagian 4.1).

A minimal supervisor runs as PID 1 in the sandbox image and starts a same-UID child that probes it:
writing to /proc/1/fd/1 (result forgery), reading /proc/1/environ and /proc/1/mem, and PTRACE_ATTACH.
Configurations vary the container's capabilities, the child's capabilities and PR_SET_DUMPABLE.

Run inside the runner container (it has the Docker SDK and socket):
  docker compose run --rm --no-deps -T -v ./scripts/profiling/supervisor_access_matrix.py:/tmp/m.py:ro runner python /tmp/m.py
Production code is not involved. Every container is removed afterwards.
"""
import json
import os
import sys
import time

import docker

IMAGE = os.getenv("SANDBOX_IMAGE", "judgementsystem-sandbox:gcc12-v4")

PROBE = r'''
import ctypes, json, os
def can(path, flags):
    try:
        os.close(os.open(path, flags))
        return True
    except OSError:
        return False
def caps(pid):
    fields = dict(line.split(":\t", 1) for line in open(f"/proc/{pid}/status").read().splitlines() if ":\t" in line)
    return fields["CapEff"].strip(), fields["CapPrm"].strip(), fields["Uid"].split()[0]
libc = ctypes.CDLL(None, use_errno=True)
print(json.dumps({
    "write_stdout": can("/proc/1/fd/1", os.O_WRONLY),
    "read_environ": can("/proc/1/environ", os.O_RDONLY),
    "read_mem": can("/proc/1/mem", os.O_RDONLY),
    "ptrace": libc.ptrace(16, 1, None, None) == 0,
    "supervisor": caps(1), "program": caps("self"),
}))
'''

SUPERVISOR = r'''
import ctypes, subprocess, sys
libc = ctypes.CDLL(None, use_errno=True)
dumpable, child_caps, probe = sys.argv[1], sys.argv[2], sys.argv[3]
if dumpable == "0":
    libc.prctl(4, 0)  # PR_SET_DUMPABLE = 0 (M1)

class Header(ctypes.Structure):
    _fields_ = [("version", ctypes.c_uint32), ("pid", ctypes.c_int)]
class Data(ctypes.Structure):
    _fields_ = [("effective", ctypes.c_uint32), ("permitted", ctypes.c_uint32), ("inheritable", ctypes.c_uint32)]

def setup():
    libc.prctl(4, 1)  # the program itself is dumpable, as in production
    if child_caps == "none":
        # Empty the bounding set first (so exec as UID 0 cannot regain capabilities), then all sets.
        for cap in range(64):
            libc.prctl(24, cap, 0, 0, 0)  # PR_CAPBSET_DROP
        header, data = Header(0x20080522, 0), (Data * 2)()
        if libc.capset(ctypes.byref(header), data) != 0:
            raise OSError(ctypes.get_errno(), "capset")

child = subprocess.run(["python3", "-I", "-c", probe], capture_output=True, text=True, preexec_fn=setup)
print(child.stdout or child.stderr, end="")
'''

CONFIGS = [
    # name, container user, cap_drop ALL?, supervisor dumpable, child capabilities, kernel step expected to decide
    ("A", "0:0", False, "1", "same", "same UID, equal capabilities: nothing denies"),
    ("B", "0:0", False, "1", "none", "same UID, supervisor holds capabilities the program lacks (step 5.2; go-judge default)"),
    ("C", "0:0", True, "1", "same", "same UID, no capabilities anywhere"),
    ("D", "65534:65534", True, "1", "same", "KodeLab without M1"),
    ("E", "65534:65534", True, "0", "same", "KodeLab with M1 (step 4)"),
]


def main():
    client = docker.from_env()
    rows = []
    try:
        for name, user, drop_all, dumpable, child_caps, meaning in CONFIGS:
            container = client.containers.run(
                IMAGE, entrypoint=["python3", "-I", "-c", SUPERVISOR], command=[dumpable, child_caps, PROBE],
                user=user, cap_drop=["ALL"] if drop_all else None, security_opt=["no-new-privileges:true"],
                network_mode="none", read_only=True, pids_limit=32, detach=True,
                # The expiry label keeps a running KodeLab runner from reaping these containers as orphans.
                labels={"judgementsystem.sandbox": "1", "judgementsystem.expires": str(time.time() + 120)})
            try:
                status = container.wait(timeout=60)["StatusCode"]
                output = container.logs(stdout=True, stderr=True).decode()
            finally:
                container.remove(force=True)
            if status != 0:
                raise RuntimeError(f"config {name} exited {status}: {output[-500:]}")
            result = json.loads(output)
            rows.append({"config": name, "meaning": meaning, "user": user, "cap_drop_all": drop_all,
                         "supervisor_dumpable": dumpable, "program_caps": child_caps, **result})
    finally:
        client.close()
    print(json.dumps(rows, indent=1))
    print()
    print(f"{'cfg':<4}{'stdout':<9}{'environ':<9}{'mem':<8}{'ptrace':<8}{'sup CapEff':<20}{'prog CapEff':<20}meaning")
    for r in rows:
        mark = lambda v: "OPEN" if v else "denied"
        print(f"{r['config']:<4}{mark(r['write_stdout']):<9}{mark(r['read_environ']):<9}{mark(r['read_mem']):<8}"
              f"{mark(r['ptrace']):<8}{r['supervisor'][0]:<20}{r['program'][0]:<20}{r['meaning']}")
    expected = {"A": True, "B": False, "C": True, "D": True, "E": False}
    wrong = [r["config"] for r in rows if r["write_stdout"] != expected[r["config"]]]
    print("\nexpected forgery outcome for every configuration" if not wrong else f"\nUNEXPECTED: {wrong}")
    sys.exit(1 if wrong else 0)


if __name__ == "__main__":
    main()
