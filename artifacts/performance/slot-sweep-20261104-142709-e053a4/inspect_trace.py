import json
from pathlib import Path

directory = Path(__file__).parent.parent / (Path(__file__).parent.name + '-slots-8')
rows = [json.loads(line) for file in (directory/'traces').glob('*.jsonl') for line in file.read_text().splitlines()]
identifier = '943a7800-1a8e-4259-a8eb-203c2098757d'
selected = [r for r in rows if r['trace'] == identifier and r['component'] == 'worker']
for r in sorted(selected, key=lambda r: r.get('at_ns', r.get('start_ns', 0))):
    print(json.dumps(r))
