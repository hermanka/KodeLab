"""Recover timing analysis from unchanged raw traces; never rerun application load."""
import json
from pathlib import Path
import shutil
import sys

directory = Path(__file__).resolve().parent
root = directory.parents[2]
sys.path.insert(0, str(root/'scripts/profiling'))
from analyze import analyze
from slot_report import write_report

manifest = json.loads((directory/'manifest.json').read_text(encoding='utf-8-sig'))
shutil.copyfile(directory/'manifest.json', directory/'manifest-before-reanalysis.json')
for entry in manifest['runs']:
    target = directory.parent/entry['directory']
    backup = target/'before-reanalysis'
    backup.mkdir()
    for name in ('stage-analysis.json', 'job-stages.csv', 'container-stages.csv', 'LAPORAN_DETAIL_RUN_SUBMIT.md'):
        if (target/name).exists():
            shutil.move(str(target/name), str(backup/name))
    analyze(target)
    raw = json.loads((target/'results.json').read_text())
    assert raw['summary']['status'] == 'completed' and not raw['summary']['anomalies']
    entry['status'] = 'completed'
    entry['analysis_note'] = 'Rejoined existing raw traces by span ancestry; original analysis preserved in before-reanalysis'
manifest['note'] = '8-slot load completed correctly; initial analyzer failed on timestamp filtering. Both cohorts reanalyzed by span ancestry without repeating load. Services restored by original finally block.'
(directory/'manifest.json').write_text(json.dumps(manifest, indent=2))
write_report(directory)
