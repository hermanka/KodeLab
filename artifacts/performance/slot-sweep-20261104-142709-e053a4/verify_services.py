"""Inspect only safe service fields; never print or persist container environment values."""
import json
from pathlib import Path
import subprocess

directory = Path(__file__).resolve().parent
manifest = json.loads((directory/'manifest.json').read_text())
expected = json.loads((directory.parent/manifest['runs'][0]['directory']/'environment.json').read_text(encoding='utf-8-sig'))['original_images']
def output(*args):
    return subprocess.check_output(['docker', *args], text=True).strip()

services = {}
for service, image in expected.items():
    identifier = output('compose', 'ps', '-q', service)
    info = json.loads(output('inspect', identifier))[0]
    assert info['Image'].removeprefix('sha256:') == image
    command = info['Config']['Cmd']
    assert not any('/profiling' in value for value in command)
    assert info['State']['Status'] == 'running'
    if service == 'worker':
        assert '--concurrency=50' in command
    services[service] = {'image': info['Image'], 'command': command, 'status': info['State']['Status']}
assert not output('ps', '-aq', '--filter', 'label=judgementsystem.sandbox=1')
(directory/'verification-services.json').write_text(json.dumps({'services': services, 'sandbox_containers_remaining': 0}, indent=2))
print('PASS original images and commands restored, worker concurrency 50, no sandbox containers remaining')
