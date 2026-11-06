"""Trusted bootstrap. Runtime replaces this process with the submitted executable.

Only source/binary and the current input enter this container. Expected answers,
runner credentials and the checker stay outside it.
"""
import base64
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
MAX_BINARY = 2 * 1024 * 1024
MAX_LOG = 16384


def compile_source(payload):
    cpp = payload["language"] == "cpp17"
    source = WORK / ("main.cpp" if cpp else "main.c")
    source.write_text(payload["source"], encoding="utf-8")
    command = ["g++" if cpp else "gcc", str(source), "-std=c++17" if cpp else "-std=c17",
               "-O2", "-Wall", "-Wextra", "-fmax-errors=10", "-o", "/work/main"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               start_new_session=True)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    output = bytearray()
    deadline = time.monotonic() + payload["compile_seconds"]
    exceeded = False
    try:
        while selector.get_map():
            if time.monotonic() > deadline:
                exceeded = True
                break
            for key, _ in selector.select(timeout=0.05):
                data = os.read(key.fileobj.fileno(), 8192)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                remaining = MAX_LOG - len(output)
                output.extend(data[:remaining])
                if len(data) > remaining:
                    exceeded = True
                    break
            if exceeded:
                break
    finally:
        if exceeded:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=2)
        selector.close()
    log = output.decode("utf-8", errors="replace")
    if exceeded:
        return {"ok": False, "log": log + "\nCompilation time or diagnostic limit exceeded."}
    if process.returncode:
        return {"ok": False, "log": log}
    binary = (WORK / "main").read_bytes()
    if len(binary) > MAX_BINARY:
        return {"ok": False, "log": "Compiled executable exceeds 2 MiB limit."}
    return {"ok": True, "log": log, "binary": base64.b64encode(binary).decode("ascii")}


def run_binary(payload):
    binary = base64.b64decode(payload["binary"], validate=True)
    if len(binary) > MAX_BINARY:
        raise ValueError("Executable too large")
    executable = WORK / "main"
    executable.write_bytes(binary)
    executable.chmod(0o500)
    input_file = WORK / "stdin"
    input_file.write_bytes(payload["input"].encode("utf-8"))
    fd = os.open(str(input_file), os.O_RDONLY)
    os.dup2(fd, 0)
    os.close(fd)
    # The remaining limits (memory, pids, wall time, output) are enforced externally.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    os.execve(str(executable), [str(executable)], {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})


def main():
    payload = json.loads(sys.stdin.buffer.readline(4 * 1024 * 1024))
    phase = payload["phase"] if sys.argv[1] == "execute" else sys.argv[1]
    if phase == "compile":
        print(json.dumps(compile_source(payload)), flush=True)
    elif phase == "run":
        run_binary(payload)
    else:
        raise ValueError("Unknown phase")


if __name__ == "__main__":
    main()
