"""Last step of every run, whatever happened before it: make sure no test runtime survives, append the ledger
row and tell kumori.ai the run is over. If the arm died before writing its row, a failed row is written here, so
a crashed or cancelled run is still on the record.
"""
import json, os, pathlib, subprocess, sys
import demo_report
from demo_report import ARM, GH_RUN, ROW_FILE, RUN_ID, RUN_URL, STARTED, _post

if ARM == 'integration':        # belt and braces: the arm deletes its own runtime; this catches a killed one
    from sweep_runtimes import sweep
    subprocess.run(['docker', 'rm', '-f', 'atom'], capture_output=True)
    deleted, refused = sweep()
    if deleted or refused: print(f'safety sweep: deleted {len(deleted)}, refused {len(refused)}')
row = json.loads(ROW_FILE.read_text()) if ROW_FILE.exists() else {
    'run_id': RUN_ID, 'arm': ARM, 'ok': False, 'summary': 'The job ended before the run could report (crashed or cancelled)', 'started': STARTED, 'ended': STARTED,
    'seconds': None, 'github_run_id': GH_RUN, 'github_run_url': RUN_URL, 'steps': []}
ledger = pathlib.Path(__file__).resolve().parents[1] / 'docs' / 'ledger' / 'runs.jsonl'
with ledger.open('a') as fh: fh.write(json.dumps(row, separators=(',', ':')) + '\n')
(pathlib.Path(os.environ.get('RUNNER_TEMP', '/tmp')) / 'commit_message').write_text(f"run {row['run_id']}: {ARM} {'passed' if row['ok'] else 'FAILED'}{f" in {row['seconds']}s" if row['seconds'] else ''}\n")
_post({'run_id': RUN_ID, 'arm': ARM, 'final': True, 'ok': row['ok'], 'summary': row['summary'], 'seconds': row['seconds'], 'github_run_id': GH_RUN, 'github_run_url': RUN_URL})
print(f"ledger row written: {ARM} {'passed' if row['ok'] else 'FAILED'}")
