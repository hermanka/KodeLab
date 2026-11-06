"""Profiling image only. Runtime still execve()s the original program as PID 1."""
import importlib.util
import resource
import subprocess
import time

spec = importlib.util.spec_from_file_location("original_judge_bootstrap", "/opt/judge/original_entrypoint.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
original_compile = base.compile_source
original_popen = subprocess.Popen
measurements = []


class TimedPopen(original_popen):
    def __init__(self, *args, **kwargs):
        self.profile_start_ns = time.time_ns()
        self.profile_start_mono = time.perf_counter_ns()
        self.profile_cpu = resource.getrusage(resource.RUSAGE_CHILDREN)
        self.profile_saved = False
        super().__init__(*args, **kwargs)

    def wait(self, *args, **kwargs):
        result = super().wait(*args, **kwargs)
        if not self.profile_saved:
            cpu = resource.getrusage(resource.RUSAGE_CHILDREN)
            measurements.append({"start_ns": self.profile_start_ns, "end_ns": time.time_ns(),
                "duration_ms": (time.perf_counter_ns()-self.profile_start_mono)/1e6,
                "cpu_ms": ((cpu.ru_utime-self.profile_cpu.ru_utime)+(cpu.ru_stime-self.profile_cpu.ru_stime))*1000})
            self.profile_saved = True
        return result


def compile_source(payload):
    result = original_compile(payload)
    if measurements:
        result["_compiler_profile"] = measurements[0]
    return result


subprocess.Popen = TimedPopen
base.compile_source = compile_source
base.main()
