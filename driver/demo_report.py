"""Tells the world what a run is doing, as it does it, and leaves one ledger row behind.

Each step is printed to the job log, posted to kumori.ai (so the page at kumori.ai/demo/boomi can show it while
the job is still running), and kept for the ledger row the workflow commits at the end. The post is
fire-and-forget: a kumori outage never fails a run. Nothing here carries an id (boomi_api.scrub).
"""
import json, os, pathlib, time, urllib.request
from datetime import datetime, timezone
from boomi_api import scrub

ARM = os.environ.get('DEMO_ARM', 'integration')
GH_RUN = os.environ.get('GITHUB_RUN_ID', 'local')
RUN_ID = os.environ.get('DEMO_RUN_ID') or f'manual-{GH_RUN}'
RUN_URL = f"https://github.com/{os.environ.get('GITHUB_REPOSITORY', 'kumori-ai/boomi-on-actions')}/actions/runs/{GH_RUN}"
EVENT_URL = 'https://kumori.ai/api/v1/boomi_demo/event'
ROW_FILE = pathlib.Path(os.environ.get('RUNNER_TEMP', '/tmp')) / 'ledger_row.json'
T0 = time.time()
STARTED = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
steps = []


def _post(body):
    key = os.environ.get('KUMORI_API_KEY')
    if not key: return
    req = urllib.request.Request(EVENT_URL, data=json.dumps(body).encode(), method='POST',
                                 headers={'X-API-Key': key, 'Content-Type': 'application/json', 'User-Agent': 'boomi-on-actions'})
    try: urllib.request.urlopen(req, timeout=8).read()
    except Exception as e: print(f'  (kumori.ai did not take the event: {type(e).__name__})', flush=True)


def step(key, label, status='done', /, **facts):
    """status: done | failed. facts are small plain values shown beside the step."""
    s = {'key': key, 'label': scrub(label), 'status': status, 't_s': round(time.time() - T0, 1), 'facts': {k: scrub(v) if isinstance(v, str) else v for k, v in facts.items()}}
    steps.append(s)
    print(f"[+{s['t_s']:5.1f}s] {'ok  ' if status == 'done' else 'FAIL'} {s['label']} {json.dumps(s['facts']) if s['facts'] else ''}", flush=True)
    _post({'run_id': RUN_ID, 'arm': ARM, 'seq': len(steps), 'github_run_id': GH_RUN, 'github_run_url': RUN_URL, **s})
    return status == 'done'


def finish(ok, summary):
    """Write the ledger row. The workflow's last step commits it and posts the final event."""
    row = {'run_id': RUN_ID, 'arm': ARM, 'ok': bool(ok), 'summary': scrub(summary), 'started': STARTED,
           'ended': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'seconds': round(time.time() - T0, 1),
           'github_run_id': GH_RUN, 'github_run_url': RUN_URL, 'steps': steps}
    ROW_FILE.write_text(json.dumps(row))
    return row
