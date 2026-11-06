"""Real Docker regression checks, enabled explicitly inside the trusted runner image."""
import os
from uuid import uuid4

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
    try:
        for identifier in created:
            with pytest.raises(NotFound):
                runner.client.containers.get(identifier)
    finally:
        for identifier in created:
            try:
                runner.client.containers.get(identifier).remove(force=True)
            except NotFound:
                pass
        runner.client.close()


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
    assert starts == created * (1+len(inputs))
    assert inspections == starts  # One final inspection per phase, independent of its duration.


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
    assert len(created) == 1 and starts == created * 3


def test_files_children_and_privileges_are_isolated_between_inputs(sandbox):
    runner, created, starts, inspections = sandbox
    source = r'''
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
int main(){
 int n;scanf("%d",&n);
 if(n==1){
  close(open("/work/marker",O_CREAT|O_WRONLY,0600));
  close(open("/tmp/marker",O_CREAT|O_WRONLY,0600));
  close(open("/dev/shm/marker",O_CREAT|O_WRONLY,0600));
  if(fork()==0){setsid();close(0);close(1);close(2);for(;;)sleep(1);}
 }else if(access("/work/marker",F_OK)==0 || access("/tmp/marker",F_OK)==0 || access("/dev/shm/marker",F_OK)==0)return 8;
 printf("%d %d %d %d\n",(int)getuid(),open("/etc/write-probe",O_CREAT|O_WRONLY,0600)==-1,
  access("/var/run/docker.sock",F_OK)==-1,getenv("RUNNER_TOKEN")==NULL);
}'''
    result = runner.judge(request(source, [("1", "65534 1 1 1"), ("2", "65534 1 1 1")]))
    assert result.verdict == "ACCEPTED"
    assert len(created) == 1 and starts == created * 3


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
    monkeypatch.setattr(runner, "execute", failed)
    with pytest.raises(RuntimeError, match="simulated"):
        runner.judge(request("int main(){}", [("", "")]))
    assert len(created) == 1 and not starts
