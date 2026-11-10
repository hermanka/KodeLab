import json
import threading
import time
from dataclasses import dataclass

import docker
from docker.errors import NotFound
from docker.types import LogConfig, Ulimit

from app.contracts import CaseResult, JudgeRequest, JudgeResult

LABEL = "judgementsystem.sandbox"


@dataclass
class Execution:
    code: int
    stdout: bytes
    stderr: bytes
    time_ms: int
    timed_out: bool
    output_exceeded: bool
    oom_killed: bool


def tokens_equal(actual: str, expected: str):
    # Preserve token boundaries. Never concatenate all whitespace-separated text.
    return actual.split() == expected.split()


class DockerRunner:
    def __init__(self, image):
        self.image = image
        self.client = docker.from_env(timeout=10)
        self.image_id = self.client.images.get(image).id

    def health(self):
        self.client.ping()
        self.client.images.get(self.image)

    def cleanup_expired(self):
        # Includes containers orphaned by controller/worker termination.
        for container in self.client.containers.list(all=True, sparse=True, filters={"label": f"{LABEL}=1"}):
            try:
                container.reload()
                deadline = float(container.labels.get("judgementsystem.expires", "0"))
                if deadline < time.time():
                    container.remove(force=True)
            except NotFound:
                pass

    def create_sandbox(self, attempt_id):
        return self.client.containers.create(
            self.image_id, command=["execute"], name=f"js-{attempt_id}",
            stdin_open=True, tty=False, network_mode="none", read_only=True,
            user="65534:65534", cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
            # Docker's default seccomp remains enabled; never use seccomp=unconfined.
            mem_limit="512m", memswap_limit="512m", nano_cpus=1_000_000_000,
            pids_limit=32, working_dir="/work", shm_size="1m",
            tmpfs={"/work": "rw,exec,nosuid,nodev,size=67108864,mode=1777", "/tmp": "rw,noexec,nosuid,nodev,size=8388608,mode=1777"},
            ulimits=[Ulimit(name="nofile", soft=64, hard=64), Ulimit(name="core", soft=0, hard=0)],
            labels={LABEL: "1", "judgementsystem.expires": str(time.time() + 180)},
            log_config=LogConfig(type="json-file", config={"max-size": "4m", "max-file": "1"}),
        )

    def execute(self, container, phase, payload, seconds, memory_mb, output_limit):
        container.update(mem_limit=f"{memory_mb}m", memswap_limit=f"{memory_mb}m")
        input_socket = None
        stream = None
        reader = None
        output = [bytearray(), bytearray()]
        overflow = threading.Event()
        read_errors = []
        stop_errors = []
        started = time.monotonic()
        timed_out = threading.Event()

        def stop_container(timeout=False):
            try:
                container.kill()
                if timeout:
                    timed_out.set()
            except docker.errors.APIError:
                # Natural exit can race the deadline/output limit; do not turn it into a timeout.
                container.reload()
                if container.status != "exited":
                    raise

        def enforce_deadline():
            try:
                stop_container(timeout=True)
            except Exception as exc:
                stop_errors.append(type(exc).__name__)

        def read_output():
            try:
                for stdout, stderr in stream:
                    for index, data in enumerate((stdout, stderr)):
                        if data:
                            used = len(output[0]) + len(output[1])
                            remaining = max(0, output_limit - used)
                            output[index].extend(data[:remaining])
                            if len(data) > remaining and not overflow.is_set():
                                overflow.set()
                                stop_container()
            except Exception as exc:
                read_errors.append(type(exc).__name__)

        try:
            # Open stdin before start. Bootstrap reads one JSON line, so no EOF is needed.
            input_socket = container.attach_socket(params={"stdin": 1, "stream": 1})
            # Attach before start without old logs: the same container has previous phases.
            stream = container.attach(stream=True, logs=False, demux=True)
            container.start()
            reader = threading.Thread(target=read_output, daemon=True)
            reader.start()
            input_socket._sock.settimeout(10)
            input_socket._sock.sendall(json.dumps({**payload, "phase": phase}).encode() + b"\n")
            watchdog = threading.Timer(seconds, enforce_deadline)
            watchdog.daemon = True
            watchdog.start()
            try:
                # This blocks on Docker's exit notification, not repeated inspect requests.
                container.wait(timeout=seconds + 15, condition="not-running")
            finally:
                watchdog.cancel()
                watchdog.join()
            container.reload()
            reader.join(timeout=5)
            if stop_errors:
                raise RuntimeError("Sandbox deadline enforcement failed")
            if reader.is_alive() or read_errors:
                raise RuntimeError("Sandbox output stream did not finish cleanly")
            state = container.attrs["State"]
            return Execution(
                code=state["ExitCode"], stdout=bytes(output[0]), stderr=bytes(output[1]),
                time_ms=int((time.monotonic() - started) * 1000),
                timed_out=timed_out.is_set(), output_exceeded=overflow.is_set(),
                oom_killed=state.get("OOMKilled", False),
            )
        finally:
            if input_socket is not None:
                input_socket.close()
            if reader:
                reader.join(timeout=2)
            # On infrastructure failure judge() force-removes the container to unblock the reader.
            if stream and (not reader or not reader.is_alive()):
                stream.close()

    def judge(self, request: JudgeRequest):
        container = self.create_sandbox(str(request.attempt_id))
        try:
            return self.judge_in_sandbox(container, request)
        finally:
            container.remove(force=True)

    def judge_in_sandbox(self, container, request: JudgeRequest):
        compile_result = self.execute(
            container, "compile",
            {"source": request.source, "language": request.language,
             "compile_seconds": request.limits.compile_seconds},
            seconds=request.limits.compile_seconds + 5, memory_mb=512, output_limit=4 * 1024 * 1024,
        )
        environment = f"{self.image_id}; profile={request.language}; checker={request.checker}"
        if compile_result.oom_killed or compile_result.timed_out or compile_result.output_exceeded:
            return JudgeResult(verdict="COMPILATION_ERROR", compile_log="Compilation resource limit exceeded.",
                               environment=environment)
        if compile_result.code:
            # Bootstrap failures are infrastructure failures, not a participant verdict.
            raise RuntimeError("Compilation bootstrap failed")
        compiled = json.loads(compile_result.stdout)
        if not compiled["ok"]:
            return JudgeResult(verdict="COMPILATION_ERROR", compile_log=compiled["log"], environment=environment)
        results = []
        for case in request.cases:
            # The time limit is CPU time (RLIMIT_CPU in the sandbox), so a busy host cannot fail a correct program.
            # Wall clock is only a backstop for sleeping/blocked programs.
            run = self.execute(
                container, "run", {"binary": compiled["binary"], "input": case.input,
                                   "cpu_seconds": request.limits.time_seconds},
                seconds=3 * request.limits.time_seconds + 2, memory_mb=request.limits.memory_mb,
                output_limit=request.limits.output_bytes,
            )
            stdout = run.stdout.decode("utf-8", errors="replace")
            stderr = run.stderr.decode("utf-8", errors="replace")
            if run.output_exceeded:
                verdict = "OUTPUT_LIMIT_EXCEEDED"
            elif run.timed_out:
                verdict = "TIME_LIMIT_EXCEEDED"
            elif run.oom_killed:
                verdict = "MEMORY_LIMIT_EXCEEDED"
            elif run.code == 137:
                # SIGKILL without OOM or a runner kill: the kernel's hard RLIMIT_CPU.
                verdict = "TIME_LIMIT_EXCEEDED"
            elif run.code:
                verdict = "RUNTIME_ERROR"
            elif request.mode == "run":
                verdict = "EXECUTED"
            elif tokens_equal(stdout, case.expected or ""):
                verdict = "ACCEPTED"
            else:
                verdict = "WRONG_ANSWER"
            results.append(CaseResult(id=case.id, verdict=verdict, stdout=stdout, stderr=stderr, time_ms=run.time_ms))
        # All cases run. First non-accepted case in package order determines aggregate verdict.
        success = "EXECUTED" if request.mode == "run" else "ACCEPTED"
        verdict = next((item.verdict for item in results if item.verdict != success), success)
        return JudgeResult(verdict=verdict, compile_log=compiled["log"], cases=results, environment=environment)
