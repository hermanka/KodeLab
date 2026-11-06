import json
import os
import sys

result = {'profiling_enabled': bool(os.getenv('JUDGE_PROFILE_DIR'))}
assert not result['profiling_enabled']
if sys.argv[1] == 'runner':
    from runner.main import slot_count
    result.update(runner_slots=slot_count, sandbox_image=os.getenv('SANDBOX_IMAGE'))
    assert slot_count == 50
    assert result['sandbox_image'] == 'judgementsystem-sandbox:gcc12-v2'
print(json.dumps(result))
