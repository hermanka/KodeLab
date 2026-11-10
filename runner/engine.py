import collections
import json
import logging
import signal
import threading
import time
from uuid import uuid4

import docker
from docker.errors import NotFound
from docker.types import LogConfig, Ulimit

from app.contracts import CaseResult, JudgeRequest, JudgeResult

LABEL = "judgementsystem.sandbox"
OUTPUT_LIMIT = 8 * 1024 * 1024  # Bootstrap JSON: compile log plus the capped output of every input.
logger = logging.getLogger(__name__)


def tokens_equal(actual: str, expected: str):
    # Preserve token boundaries. Never concatenate all whitespace-separated text.
    return actual.split() == expected.split()


class Sandbox:
    """A started container whose bootstrap waits for one payload on stdin and answers with one JSON line."""

    def __init__(self, container):
        self.container = container
        self.output = bytearray()
        self.done = threading.Event()
        self.input_socket = self.stream = self.reader = None
        try:
            # Open stdin before start. Bootstrap reads one JSON line, so no EOF is needed.
            self.input_socket = container.attach_socket(params={"stdin": 1, "stream": 1})
            self.stream = container.attach(stream=True, logs=False, demux=True)
            container.start()
            self.reader = threading.Thread(target=self.read_output, daemon=True)
            self.reader.start()
        except BaseException:
            self.close()
            raise

    def read_output(self):
        try:
            # Only the bootstrap can write here (the program cannot reach PID 1's stdout); stderr is not a result.
            for stdout, _ in self.stream:
                if stdout:
                    self.output.extend(stdout)
                    if b"\n" in stdout or len(self.output) > OUTPUT_LIMIT:
                        break
        except Exception as exc:
            logger.warning("Sandbox output stream failed: %s", type(exc).__name__)
        finally:
            self.done.set()

    def run(self, payload, seconds):
        """The bootstrap's answer. It enforces every participant limit itself, so a missing, late or
        oversized answer is an infrastructure failure, never a verdict. Returns as soon as the answer
        line arrives: waiting for and removing the container is not on the participant's clock."""
        self.input_socket._sock.settimeout(10)
        self.input_socket._sock.sendall(json.dumps(payload).encode() + b"\n")
        if not self.done.wait(seconds) or not self.output.endswith(b"\n") or len(self.output) > OUTPUT_LIMIT:
            raise RuntimeError("Sandbox bootstrap failed")
        return json.loads(self.output)

    def close(self):
        if self.input_socket is not None:
            self.input_socket.close()
        if self.reader:
            self.reader.join(timeout=2)
        # The caller force-removes the container first, which ends the stream a reader may still block on.
        if self.stream and (not self.reader or not self.reader.is_alive()):
            self.stream.close()


class DockerRunner:
    def __init__(self, image, warm=0):
        self.image = image
        self.client = docker.from_env(timeout=10)
        self.image_id = self.client.images.get(image).id
        # Warm pool: sandboxes created and started ahead of time, so a job only pays for compiling and running.
        # Every job still gets its own container; nothing is reused between jobs.
        self.warm, self.pool, self.trash = warm, collections.deque(), collections.deque()
        self.live, self.running = set(), set()
        self.closed, self.work = threading.Event(), threading.Event()
        self.maintainer = threading.Thread(target=self.maintain, daemon=True)
        self.maintainer.start()

    def health(self):
        self.client.ping()
        self.client.images.get(self.image)

    def close(self):
        self.closed.set()
        self.work.set()
        self.maintainer.join(timeout=30)  # Finishes pending removals and any refill already in flight.
        # In parallel: the whole pool must be gone within the container's stop grace period.
        removals = [threading.Thread(target=self.discard, args=(sandbox,)) for sandbox in self.pool]
        self.pool.clear()
        for thread in removals:
            thread.start()
        for thread in removals:
            thread.join()
        self.client.close()

    def maintain(self):
        # One background thread removes finished sandboxes and prepares new ones, so neither is on a
        # participant's clock, and refilling waits for running jobs unless the pool is empty.
        while True:
            self.work.clear()
            try:
                if self.trash:
                    self.discard(self.trash.popleft())
                elif self.closed.is_set():
                    return
                elif len(self.pool) < self.warm and not (self.running and self.pool):
                    self.pool.append(self.prepare(f"warm-{uuid4()}"))
                else:
                    self.work.wait()
            except Exception as exc:
                logger.warning("Sandbox maintenance failed: %s", type(exc).__name__)
                self.closed.wait(1)

    def cleanup_expired(self):
        # Includes containers orphaned by controller/worker termination. Live ones (warm or running) are ours.
        for container in self.client.containers.list(all=True, sparse=True, filters={"label": f"{LABEL}=1"}):
            if container.id in self.live:
                continue
            try:
                container.reload()
                deadline = float(container.labels.get("judgementsystem.expires", "0"))
                if deadline < time.time():
                    container.remove(force=True)
            except NotFound:
                pass

    def create_sandbox(self, name):
        return self.client.containers.create(
            self.image_id, name=f"js-{name}",
            stdin_open=True, tty=False, network_mode="none", read_only=True,
            user="65534:65534", cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
            # Docker's default seccomp remains enabled; never use seccomp=unconfined.
            # 512 MiB is the compiler's ceiling; the bootstrap enforces a problem's own memory limit.
            mem_limit="512m", memswap_limit="512m", nano_cpus=1_000_000_000,
            pids_limit=32, working_dir="/work", shm_size="1m",
            # All inputs share one container start: no IPC object may outlive a process and carry data to the next input.
            sysctls={"kernel.shmmni": "0", "kernel.msgmni": "0", "kernel.sem": "0 0 0 0", "fs.mqueue.queues_max": "0"},
            tmpfs={"/work": "rw,exec,nosuid,nodev,size=67108864,nr_inodes=4096,mode=1777",
                   "/tmp": "rw,noexec,nosuid,nodev,size=8388608,nr_inodes=4096,mode=1777"},
            ulimits=[Ulimit(name="nofile", soft=64, hard=64), Ulimit(name="core", soft=0, hard=0)],
            labels={LABEL: "1", "judgementsystem.expires": str(time.time() + 180)},
            log_config=LogConfig(type="json-file", config={"max-size": "4m", "max-file": "1"}),
        )

    def prepare(self, name):
        container = self.create_sandbox(name)
        self.live.add(container.id)
        try:
            return Sandbox(container)
        except BaseException:
            self.remove(container)
            raise

    def remove(self, container):
        try:
            container.remove(force=True)  # Also kills whatever is still running in it.
        finally:
            self.live.discard(container.id)

    def discard(self, sandbox):
        try:
            self.remove(sandbox.container)
        finally:
            sandbox.close()

    def judge_once(self, sandbox, request):
        self.running.add(sandbox)
        try:
            return self.judge_in_sandbox(sandbox, request)
        finally:
            self.running.discard(sandbox)
            self.trash.append(sandbox)
            self.work.set()

    def judge(self, request: JudgeRequest):
        try:
            sandbox = self.pool.popleft()
        except IndexError:
            sandbox = None
        self.work.set()  # An emptied pool is refilled even while jobs run.
        if sandbox:
            try:
                return self.judge_once(sandbox, request)
            except Exception as exc:
                # A warm sandbox can die while idle (for example a Docker restart): retry once on a fresh one.
                logger.warning("Warm sandbox failed, retrying cold: %s", type(exc).__name__)
        return self.judge_once(self.prepare(str(request.attempt_id)), request)

    def judge_in_sandbox(self, sandbox, request: JudgeRequest):
        limits = request.limits
        # The time limit is CPU time, so a busy host cannot fail a correct program.
        # Wall clock is only a backstop for sleeping/blocked programs; 10 cases at the 5 s maximum must still
        # finish inside the worker's 140 s HTTP timeout.
        wall = 2 * limits.time_seconds + 1
        outcome = sandbox.run(
            {"source": request.source, "language": request.language, "compile_seconds": limits.compile_seconds,
             "inputs": [case.input for case in request.cases], "cpu_seconds": limits.time_seconds,
             "wall_seconds": wall, "memory_mb": limits.memory_mb, "output_bytes": limits.output_bytes},
            seconds=limits.compile_seconds + len(request.cases) * wall + 10,
        )
        environment = f"{self.image_id}; profile={request.language}; checker={request.checker}"
        if not outcome["ok"]:
            return JudgeResult(verdict="COMPILATION_ERROR", compile_log=outcome["log"], environment=environment)
        results = []
        for case, item in zip(request.cases, outcome["cases"], strict=True):
            if item["output_exceeded"]:
                verdict = "OUTPUT_LIMIT_EXCEEDED"
            elif item["memory_exceeded"]:
                # shortcut: resident memory is measured per process, so a program that forks can use up to the
                # 512 MiB container ceiling without this verdict; count the whole process tree if that ever matters.
                verdict = "MEMORY_LIMIT_EXCEEDED"
            elif item["timed_out"] or item["exit"] == -signal.SIGXCPU or item["cpu_ms"] >= limits.time_seconds * 1000:
                verdict = "TIME_LIMIT_EXCEEDED"
            elif item["exit"] == -signal.SIGKILL:
                # A SIGKILL the bootstrap did not send is the container's OOM killer.
                verdict = "MEMORY_LIMIT_EXCEEDED"
            elif item["exit"]:
                verdict = "RUNTIME_ERROR"
            elif request.mode == "run":
                verdict = "EXECUTED"
            elif tokens_equal(item["stdout"], case.expected or ""):
                verdict = "ACCEPTED"
            else:
                verdict = "WRONG_ANSWER"
            results.append(CaseResult(id=case.id, verdict=verdict, stdout=item["stdout"], stderr=item["stderr"],
                                      time_ms=item["cpu_ms"]))
        # All cases run. First non-accepted case in package order determines aggregate verdict.
        success = "EXECUTED" if request.mode == "run" else "ACCEPTED"
        verdict = next((item.verdict for item in results if item.verdict != success), success)
        return JudgeResult(verdict=verdict, compile_log=outcome["log"], cases=results, environment=environment)
