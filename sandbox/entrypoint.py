"""Trusted bootstrap: PID 1 compiles once, then runs every input as a fresh child process.

Only source and inputs enter this container. Expected answers, runner credentials and the
checker stay outside it. The submitted program shares the container with this bootstrap, so
isolation between inputs is explicit instead of coming from a container restart:
- the bootstrap is non-dumpable: no ptrace, no /proc/1 access, so results cannot be forged
  and later inputs cannot be read from its memory;
- after every child, every other process is killed and all writable directories are wiped;
- the runner disables SysV/POSIX IPC objects for the container (see create_sandbox).
"""
import ctypes
import glob
import json
import os
from pathlib import Path
import resource
import selectors
import signal
import subprocess
import sys
import time

WORK = Path("/work")
WRITABLE = ("/work", "/tmp", "/dev/shm")
MAX_BINARY = 2 * 1024 * 1024
MAX_LOG = 16384
PR_SET_DUMPABLE = 4
C_FLAGS = ["-std=c17", "-O2", "-Wall", "-Wextra", "-fmax-errors=10"]
CPP_FLAGS = ["-std=c++17", "-O2", "-Wall", "-Wextra", "-fmax-errors=10"]
PCH = "/opt/pch"  # Precompiled <iostream> and <bits/stdc++.h>: GCC uses one when it is the first include.
PAGE_KB = os.sysconf("SC_PAGE_SIZE") // 1024
libc = ctypes.CDLL(None, use_errno=True)


def child_setup(cpu_seconds):
    def setup():
        # /proc/self is root-owned while non-dumpable. Safe: no untrusted process is alive during a fork.
        libc.prctl(PR_SET_DUMPABLE, 1)
        with open("/proc/self/oom_score_adj", "w") as score:
            score.write("1000")  # A container OOM must kill the child, never PID 1.
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        if cpu_seconds:
            # Soft limit raises SIGXCPU (an unambiguous time-limit exit); the hard limit stops handlers.
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
            resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    return setup


def sweep():
    """As PID 1, SIGKILL reaches every other process in the container, including daemonized ones."""
    try:
        os.kill(-1, signal.SIGKILL)
    except ProcessLookupError:
        pass
    while True:
        try:
            os.waitpid(-1, 0)
        except ChildProcessError:
            return


def remove(path):
    if not os.path.isdir(path) or os.path.islink(path):
        os.unlink(path)
        return
    os.chmod(path, 0o700)
    with os.scandir(path) as entries:
        for entry in entries:
            remove(entry.path)
    os.rmdir(path)


def wipe():
    # shortcut: a hostile tree (path beyond PATH_MAX, depth beyond the recursion limit) raises and fails
    # only that submission as an infrastructure error; handle it here if that ever needs a verdict.
    for root in WRITABLE:
        with os.scandir(root) as entries:
            for entry in entries:
                remove(entry.path)


def supervise(command, stdin, output_limit, wall_seconds, cpu_seconds=None, memory_kb=None, merge=False, env=None):
    """Run one child to completion or to a limit, then leave no process behind."""
    process = subprocess.Popen(
        command, stdin=stdin, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if merge else subprocess.PIPE,
        start_new_session=True, env=env, preexec_fn=child_setup(cpu_seconds))
    streams = [process.stdout] if merge else [process.stdout, process.stderr]
    output = [bytearray() for _ in streams]
    pidfd = os.pidfd_open(process.pid)
    selector = selectors.DefaultSelector()
    selector.register(pidfd, selectors.EVENT_READ, None)
    for index, stream in enumerate(streams):
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ, index)
    exceeded = False

    def read(index):
        """False at end of stream or when nothing is buffered."""
        nonlocal exceeded
        try:
            data = os.read(streams[index].fileno(), 65536)
        except BlockingIOError:
            return False
        remaining = output_limit - sum(len(part) for part in output)
        output[index].extend(data[:max(0, remaining)])
        exceeded = exceeded or len(data) > remaining
        return bool(data)

    started = time.monotonic()
    exited = timed_out = memory_exceeded = False
    try:
        while not (exited or timed_out or exceeded or memory_exceeded):
            remaining = started + wall_seconds - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            if memory_kb:
                # The container limit is the compiler's 512 MiB, so the problem's limit is enforced by polling.
                with open(f"/proc/{process.pid}/statm") as statm:
                    memory_exceeded = int(statm.read().split()[1]) * PAGE_KB > memory_kb
                remaining = min(remaining, 0.02)
            for key, _ in selector.select(remaining):
                if key.data is None:
                    exited = True
                elif not read(key.data):
                    selector.unregister(key.fileobj)
        if not exited:
            os.kill(process.pid, signal.SIGKILL)
        _, status, usage = os.wait4(process.pid, 0)
        process.returncode = os.waitstatus_to_exitcode(status)
        if exited:  # Output written just before a normal exit is still buffered in the pipes.
            for index in range(len(streams)):
                while not exceeded and read(index):
                    pass
    finally:
        selector.close()
        os.close(pidfd)
        for stream in streams:
            stream.close()
        sweep()
    return {
        "exit": process.returncode, "timed_out": timed_out, "output_exceeded": exceeded,
        "memory_exceeded": memory_exceeded or bool(memory_kb and usage.ru_maxrss > memory_kb),
        "cpu_ms": int((usage.ru_utime + usage.ru_stime) * 1000),
        "output": [part.decode("utf-8", errors="replace") for part in output],
    }


def compile_source(payload):
    cpp = payload["language"] == "cpp17"
    source = WORK / ("main.cpp" if cpp else "main.c")
    source.write_text(payload["source"], encoding="utf-8")
    command = (["g++", str(source), *CPP_FLAGS, "-I", PCH] if cpp else ["gcc", str(source), *C_FLAGS]) + ["-o", "/work/main"]
    result = supervise(command, subprocess.DEVNULL, MAX_LOG, payload["compile_seconds"], merge=True)
    log = result["output"][0]
    if result["timed_out"] or result["output_exceeded"]:
        return {"ok": False, "log": log + "\nCompilation time or diagnostic limit exceeded."}
    if result["exit"]:
        return {"ok": False, "log": log or "Compilation resource limit exceeded."}
    binary = (WORK / "main").read_bytes()
    if len(binary) > MAX_BINARY:
        return {"ok": False, "log": "Compiled executable exceeds 2 MiB limit."}
    return {"ok": True, "log": log, "binary": binary}


def run_case(binary, text, payload):
    wipe()  # Also restores the executable: a previous input may have replaced it.
    executable = WORK / "main"
    executable.write_bytes(binary)
    executable.chmod(0o500)
    input_file = WORK / "stdin"
    input_file.write_bytes(text.encode("utf-8"))
    with open(input_file, "rb") as stdin:
        result = supervise([str(executable)], stdin, payload["output_bytes"], payload["wall_seconds"],
                           cpu_seconds=payload["cpu_seconds"], memory_kb=payload["memory_mb"] * 1024,
                           env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
    result["stdout"], result["stderr"] = result.pop("output")
    return result


def build_pch():
    """Image build step. Uses the flags of every later compilation: GCC silently ignores a header built with others."""
    for name, pattern in (("iostream", "/usr/include/c++/*/iostream"), ("bits/stdc++.h", "/usr/include/*/c++/*/bits/stdc++.h")):
        header, = glob.glob(pattern)
        stub, target = f"{PCH}/{name}", f"{PCH}/{name}.gch"
        os.makedirs(os.path.dirname(stub), exist_ok=True)
        # A real header beside the .gch: a repeated or nested include of the same name must still resolve.
        Path(stub).write_text(f'#include "{header}"\n')
        subprocess.run(["g++", *CPP_FLAGS, "-x", "c++-header", stub, "-o", target], check=True)
        probe = subprocess.run(["g++", *CPP_FLAGS, "-I", PCH, "-H", "-fsyntax-only", "-x", "c++", "-"],
                               input=f"#include <{name}>\nint main(){{}}\n", text=True, capture_output=True, check=True)
        assert f"! {target}" in probe.stderr, f"GCC does not use {target}"


def main():
    if sys.argv[1:] == ["pch"]:
        return build_pch()
    libc.prctl(PR_SET_DUMPABLE, 0)
    # Python's SIGINT handler would let the program interrupt PID 1; with the default action the kernel drops it.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    assert os.getpid() == 1, "The bootstrap must be the container's init process"
    payload = json.loads(sys.stdin.buffer.readline(4 * 1024 * 1024))
    compiled = compile_source(payload)
    result = {"ok": compiled["ok"], "log": compiled["log"]}
    if compiled["ok"]:
        result["cases"] = [run_case(compiled["binary"], text, payload) for text in payload["inputs"]]
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
