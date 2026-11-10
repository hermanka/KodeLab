"""Real Docker regression checks, enabled explicitly inside the trusted runner image."""
import os
import time
from uuid import uuid4

import docker
import pytest
from docker.errors import NotFound
from docker.models.containers import Container, ContainerCollection

from app.contracts import Case, JudgeRequest, Limits
from runner.engine import DockerRunner

pytestmark = pytest.mark.skipif(os.getenv("RUN_SANDBOX_TESTS") != "1", reason="Requires real Docker sandbox")


@pytest.fixture
def sandbox(monkeypatch):
    runner = DockerRunner(os.environ["SANDBOX_IMAGE"])
    created, starts, inspections = [], [], []
    create, start, reload = ContainerCollection.create, Container.start, Container.reload

    def tracked_create(collection, *args, **kwargs):
        container = create(collection, *args, **kwargs)
        created.append(container.id)
        return container

    def tracked_start(container, *args, **kwargs):
        starts.append(container.id)
        return start(container, *args, **kwargs)

    def tracked_reload(container, *args, **kwargs):
        inspections.append(container.id)
        return reload(container, *args, **kwargs)

    monkeypatch.setattr(ContainerCollection, "create", tracked_create)
    monkeypatch.setattr(Container, "start", tracked_start)
    monkeypatch.setattr(Container, "reload", tracked_reload)
    yield runner, created, starts, inspections
    leftovers = []
    try:
        runner.close()  # Waits for the background removal of every finished sandbox.
        assert not runner.live
    finally:
        client = docker.from_env()
        for identifier in created:
            try:
                client.containers.get(identifier).remove(force=True)
                leftovers.append(identifier)
            except NotFound:
                pass
        client.close()
    assert not leftovers


def request(source, inputs, mode="judge", language="c17"):
    return JudgeRequest(attempt_id=uuid4(), source=source, language=language, mode=mode,
        limits=Limits(time_seconds=1, memory_mb=64, output_bytes=1024),
        cases=[Case(id=str(i), input=value, expected=expected, public=True)
               for i, (value, expected) in enumerate(inputs)])


@pytest.mark.parametrize("language,source", [
    ("c17", '#include <stdio.h>\n#warning compile-note\nint main(){int a,b;scanf("%d%d",&a,&b);printf("%d\\n",a+b);}'),
    ("cpp17", '#include <iostream>\nint main(){int a,b;std::cin>>a>>b;std::cout<<a+b<<"\\n";}')])
@pytest.mark.parametrize("mode", ["run", "judge"])
def test_one_container_for_compile_and_all_inputs(sandbox, language, source, mode):
    runner, created, starts, inspections = sandbox
    inputs = [("2 3", "5")] if mode == "run" else [("2 3", "5"), ("-7 -8", "-15"), ("0 0", "0")]
    result = runner.judge(request(source, inputs, mode, language))
    assert result.verdict == ("EXECUTED" if mode == "run" else "ACCEPTED")
    assert [r.stdout.strip() for r in result.cases] == [expected for _, expected in inputs]
    assert all(not r.stderr for r in result.cases)
    if language == "c17":
        assert "compile-note" in result.compile_log
    assert len(created) == 1
    assert starts == created  # One start covers compilation and every input.
    assert not inspections  # The answer line is enough: no wait or inspect on the participant's clock.


@pytest.mark.parametrize("action,verdict", [
    ("return 7;", "RUNTIME_ERROR"),
    ('puts("wrong");return 0;', "WRONG_ANSWER"),
    ("for(;;){}", "TIME_LIMIT_EXCEEDED"),
    ('for(;;)puts("0123456789");', "OUTPUT_LIMIT_EXCEEDED"),
    ("for(;;){volatile char *p=malloc(1048576);if(!p)return 19;for(int i=0;i<1048576;i+=4096)p[i]=1;}", "MEMORY_LIMIT_EXCEEDED")])
def test_resource_failure_does_not_contaminate_next_input(sandbox, action, verdict):
    runner, created, starts, inspections = sandbox
    source = '#include <stdio.h>\n#include <stdlib.h>\nint main(){int n;scanf("%d",&n);if(n==1){'+action+'}puts("OK");}'
    result = runner.judge(request(source, [("1", "OK"), ("2", "OK")]))
    assert result.verdict == verdict
    assert [r.verdict for r in result.cases] == [verdict, "ACCEPTED"]
    assert result.cases[1].stdout.strip() == "OK"
    assert len(result.cases[0].stdout.encode())+len(result.cases[0].stderr.encode()) <= 1024
    assert len(created) == 1 and starts == created


def test_files_children_and_privileges_are_isolated_between_inputs(sandbox):
    runner, created, starts, inspections = sandbox
    source = r'''
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
int main(){
 int n;scanf("%d",&n);
 if(n==1){
  close(open("/work/marker",O_CREAT|O_WRONLY,0600));
  close(open("/tmp/marker",O_CREAT|O_WRONLY,0600));
  close(open("/dev/shm/marker",O_CREAT|O_WRONLY,0600));
  if(fork()==0){setsid();close(0);close(1);close(2);for(;;)sleep(1);}
  /* Replace the executable and its input for the next case. */
  chmod("/work/main",0700);unlink("/work/main");symlink("/bin/false","/work/main");
  mkdir("/work/locked",0700);close(open("/work/locked/inner",O_CREAT|O_WRONLY,0600));chmod("/work/locked",0);
 }else if(access("/work/marker",F_OK)==0 || access("/tmp/marker",F_OK)==0 || access("/dev/shm/marker",F_OK)==0
          || access("/work/locked",F_OK)==0)return 8;
 printf("%d %d %d %d\n",(int)getuid(),open("/etc/write-probe",O_CREAT|O_WRONLY,0600)==-1,
  access("/var/run/docker.sock",F_OK)==-1,getenv("RUNNER_TOKEN")==NULL);
}'''
    result = runner.judge(request(source, [("1", "65534 1 1 1"), ("2", "65534 1 1 1")]))
    assert result.verdict == "ACCEPTED"
    assert len(created) == 1 and starts == created


def test_compilation_failure_removes_the_only_container(sandbox):
    runner, created, starts, inspections = sandbox
    result = runner.judge(request("int main( {", [("", "")], language="cpp17"))
    assert result.verdict == "COMPILATION_ERROR" and not result.cases
    assert result.compile_log
    assert len(created) == 1 and starts == created


def test_infrastructure_failure_still_removes_container(sandbox, monkeypatch):
    runner, created, starts, inspections = sandbox
    def failed(*args, **kwargs):
        raise RuntimeError("simulated infrastructure failure")
    monkeypatch.setattr(runner, "judge_in_sandbox", failed)
    with pytest.raises(RuntimeError, match="simulated"):
        runner.judge(request("int main(){}", [("", "")]))
    assert len(created) == 1


def test_program_cannot_reach_the_bootstrap_or_keep_kernel_objects(sandbox):
    """All inputs share one start: the program must not forge results, read later inputs or leave IPC objects."""
    runner, created, starts, inspections = sandbox
    source = r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <signal.h>
#include <unistd.h>
#include <fcntl.h>
#include <mqueue.h>
#include <sys/ipc.h>
#include <sys/shm.h>
#include <sys/msg.h>
#include <sys/sem.h>
#include <sys/ptrace.h>
#include <sys/syscall.h>
int main(){
 int n;scanf("%d",&n);
 kill(1,SIGINT);kill(1,SIGTERM);kill(1,SIGKILL);kill(1,SIGSTOP);
 int forged=open("/proc/1/fd/1",O_WRONLY);
 if(forged>=0)dprintf(forged,"{\"ok\":true,\"log\":\"\",\"cases\":[]}\n");
 printf("%d %d %d %d %d %d %d %d %d\n",forged,open("/proc/1/mem",O_RDONLY),open("/proc/1/environ",O_RDONLY),
  (int)ptrace(PTRACE_ATTACH,1,0,0),shmget(IPC_PRIVATE,4096,IPC_CREAT|0600),msgget(IPC_PRIVATE,IPC_CREAT|0600),
  semget(IPC_PRIVATE,1,IPC_CREAT|0600),(int)mq_open("/leak",O_CREAT|O_RDWR,0600,NULL),
  (int)syscall(SYS_add_key,"user","leak","x",1,-4));
}'''
    denied = "-1 -1 -1 -1 -1 -1 -1 -1 -1"
    result = runner.judge(request(source, [("1", denied), ("2", denied)]))
    assert [(r.verdict, r.stdout.strip()) for r in result.cases] == [("ACCEPTED", denied)] * 2


def test_wall_clock_backstop_stops_a_sleeping_program(sandbox):
    runner, created, starts, inspections = sandbox
    source = '#include <stdio.h>\n#include <unistd.h>\nint main(){int n;scanf("%d",&n);if(n==1)sleep(60);puts("OK");}'
    result = runner.judge(request(source, [("1", "OK"), ("2", "OK")]))
    assert [r.verdict for r in result.cases] == ["TIME_LIMIT_EXCEEDED", "ACCEPTED"]


@pytest.mark.parametrize("header", ["bits/stdc++.h", "iostream", "vector"])
def test_precompiled_headers_do_not_change_results(sandbox, header):
    """<bits/stdc++.h> and <iostream> come from /opt/pch when they are the first include; <vector> first does not."""
    runner, created, starts, inspections = sandbox
    source = ('#include <' + header + '>\n#include <iostream>\n#include <vector>\n#include <algorithm>\n#include <bits/stdc++.h>\n'
              'int main(){std::vector<long long> v(2);std::cin>>v[0]>>v[1];std::sort(v.begin(),v.end());'
              'std::cout<<v[0]+v[1]<<"\\n";}')
    result = runner.judge(request(source, [("2 3", "5"), ("-7 -8", "-15")], language="cpp17"))
    assert result.verdict == "ACCEPTED" and not result.compile_log


def test_warm_pool_gives_each_job_its_own_prepared_container_and_cleans_up():
    runner = DockerRunner(os.environ["SANDBOX_IMAGE"], warm=2)
    source = '#include <stdio.h>\nint main(){int a,b;scanf("%d%d",&a,&b);printf("%d\\n",a+b);}'
    try:
        for _ in range(100):
            if len(runner.pool) == 2:
                break
            time.sleep(0.1)
        prepared = [sandbox.container.id for sandbox in runner.pool]
        assert len(prepared) == 2 and set(prepared) == runner.live
        runner.cleanup_expired()  # Must never reap live sandboxes, whatever their label says.
        for identifier in prepared:  # FIFO: each job consumes exactly one prepared container.
            assert runner.pool[0].container.id == identifier
            assert runner.judge(request(source, [("2 3", "5"), ("4 5", "9")])).verdict == "ACCEPTED"
        for _ in range(100):
            if len(runner.pool) == 2:
                break
            time.sleep(0.1)
        refilled = [sandbox.container.id for sandbox in runner.pool]
        assert len(refilled) == 2 and not set(refilled) & set(prepared)
        for identifier in prepared:  # Used sandboxes are removed in the background, never reused.
            with pytest.raises(NotFound):
                runner.client.containers.get(identifier)
        # A warm sandbox that died while idle is replaced by a fresh one instead of failing the job.
        runner.pool[0].container.kill()
        assert runner.judge(request(source, [("2 3", "5")])).verdict == "ACCEPTED"
    finally:
        runner.close()
    assert not runner.live and not runner.pool
