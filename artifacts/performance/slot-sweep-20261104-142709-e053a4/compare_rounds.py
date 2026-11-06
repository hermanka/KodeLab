"""Validate and summarize two opposite-order rounds without changing older artifacts."""
import hashlib
import json
from pathlib import Path
import sys

directory = Path(__file__).resolve().parent
root = directory.parents[2]
sys.path.insert(0, str(root/'scripts/profiling'))
from analyze import stats

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

previous = directory.parent/'slot-sweep-20261104-122722-9e1850'
rounds = [read(p/'comparison.json') for p in (previous, directory)]
images, combined, warnings = [], {}, {}
for capacity in (8, 12):
    measurements = {phase: [] for phase in ('run_30', 'submit_30')}
    for round_ in rounds:
        entry = next(r for r in round_['runs'] if r['slots'] == capacity)
        target = directory.parent/entry['directory']
        images.append(read(target/'environment.json')['original_images'])
        analysis = read(target/'stage-analysis.json')
        assert not analysis['issues'] and analysis['jobs_joined'] == 64
        for phase in measurements:
            measurements[phase].extend(j['first_try_to_client_ms'] for j in analysis['job_rows'] if j['phase'] == phase)
        log = (target/'service-profile.log').read_text(encoding='utf-8-sig')
        warnings[entry['directory']] = {term: log.count(term) for term in ('Sandbox cleanup error', 'Judging failed', 'PROFILE_WRITE_FAILED')}
        assert not any(warnings[entry['directory']].values())
    assert all(len(values) == 60 for values in measurements.values())
    combined[capacity] = {phase: stats(values) for phase, values in measurements.items()}
assert all(value == images[0] for value in images)
new_targets = [directory.parent/r['directory'] for r in read(directory/'manifest.json')['runs']]
secret_values = []
for line in (root/'.env').read_text().splitlines():
    key, sep, value = line.partition('=')
    if sep and any(term in key.upper() for term in ('PASSWORD', 'TOKEN', 'SECRET')) and len(value.strip()) >= 8:
        secret_values.append(value.strip())
for target in [directory, *new_targets]:
    for file in target.rglob('*'):
        if file.is_file():
            data = file.read_bytes()
            assert all(value.encode() not in data for value in secret_values), 'Configured secret found in artifacts'
result = {'pooled_first_try_ms': combined, 'images_identical_across_four_cohorts': True,
          'main_jobs_correct_this_round': 128, 'warnings': warnings,
          'database': read(directory/'verification-database.json'),
          'runner': read(directory/'verification-runner.json'), 'api': read(directory/'verification-api.json'),
          'configured_secret_scan': 'passed',
          'source_hashes': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in [root/'compose.yaml', root/'scripts/profiling/analyze.py', root/'scripts/profiling/check.py']}}
(directory/'verification.json').write_text(json.dumps(result, indent=2))
print(json.dumps(combined, indent=2))
