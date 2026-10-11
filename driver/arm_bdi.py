"""Data Integration (Rivery): read the pipelines and their latest runs from the runner.

Lists every pipeline, then reads the most recent run of each: its status, how long it took and the credits it
was billed. Read-only, so it spends no credits: starting a pipeline is the step that costs, and that proof is in
the receipts (docs/receipts/bdi_*).
"""
import json, os, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from demo_report import finish, step

BASE = f"https://api.rivery.io/v1/accounts/{os.environ['BDI_ACCOUNT']}/environments/{os.environ['BDI_ENV']}"


def get(path, token=True):
    req = urllib.request.Request(BASE + path, headers={'Accept': 'application/json', **({'Authorization': 'Bearer ' + os.environ['BDI_TOKEN']} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r: return r.status, json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e: return e.code, {}


def main():
    t = time.time()
    code, d = get('/rivers')
    rows = d.get('items', []) if isinstance(d, dict) else []
    if not step('list', 'Listed the pipelines (zero would be a failure, not a pass)', 'done' if code == 200 and rows else 'failed', http=code, pipelines=len(rows),
                active=sum(1 for r in rows if r.get('river_status') == 'active')): return False
    now = datetime.now(timezone.utc)
    q = urllib.parse.urlencode({'start_time': (now - timedelta(days=14)).strftime('%Y-%m-%dT%H:%M:%S'), 'end_time': now.strftime('%Y-%m-%dT%H:%M:%S')})
    seen = 0
    for r in sorted(rows, key=lambda r: str(r.get('name'))):
        code, runs = get(f"/rivers/{r.get('river_cross_id') or r.get('cross_id')}/runs?{q}")
        items = runs.get('items', []) if code == 200 else []
        last = items[0] if items else {}
        seen += len(items)
        step(f"runs_{str(r.get('name'))[:2].strip()}", f"Read the run history of: {str(r.get('name'))[:60]}", 'done' if code == 200 else 'failed',
             runs_in_14_days=len(items), latest=last.get('status'), credits_billed=last.get('units'), started=last.get('start_date_utc'))
    ok = step('history', 'Read real run records, with the credits each was billed', 'done' if seen else 'failed', runs_read=seen)
    code, _ = get('/rivers', token=False)
    ok &= step('canary', 'Asked again with no token: refused, so the answers needed it', 'done' if code in (401, 403) else 'failed', http=code)
    return ok and step('clean', 'Read-only: no pipeline was started and no credits were spent', total_seconds=round(time.time() - t, 1))


if __name__ == '__main__':
    ok = False
    try: ok = bool(main())
    except Exception as e: step('crashed', 'The script stopped on an error', 'failed', error=f'{type(e).__name__}: {e}'[:160])
    finally: finish(ok, 'A runner read the Data Integration pipelines and their run records' if ok else 'The run did not hold: see the failed step')
    sys.exit(0 if ok else 1)
