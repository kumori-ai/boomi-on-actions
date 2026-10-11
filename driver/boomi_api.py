"""Thin Boomi Platform API helper for the pipeline. Reads BOOMI_API_USER, BOOMI_API_TOKEN and BOOMI_IDS (a JSON
object of account, environment and process ids) from the environment; in this repo those are repository secrets.

Every id is registered as a log mask on import, so nothing this job prints can carry one, whatever Boomi's own
error messages say.
"""
import json, os, time
import requests

IDS = json.loads(os.environ['BOOMI_IDS'])
ACCT = IDS['account']
BASE = f'https://api.boomi.com/api/rest/v1/{ACCT}'
H = {'Accept': 'application/json', 'Content-Type': 'application/json'}
_u = os.environ['BOOMI_API_USER']
AUTH = (_u if _u.startswith('BOOMI_TOKEN.') else 'BOOMI_TOKEN.' + _u, os.environ['BOOMI_API_TOKEN'])
_OTHER = {os.environ.get(k, '') for k in ('FLOW_TENANT', 'FLOW_ID', 'BDI_ACCOUNT', 'BDI_ENV')}      # ids the other arms use
SECRET_WORDS = sorted({str(v) for v in IDS.values() if isinstance(v, str) and len(v) >= 6} | {_u.replace('BOOMI_TOKEN.', '')} | {w for w in _OTHER if len(w) >= 6}, key=len, reverse=True)
if os.environ.get('GITHUB_ACTIONS'):
    for _w in SECRET_WORDS: print(f'::add-mask::{_w}')


def scrub(text):
    """The same masking, applied to anything that leaves the job by another road (the ledger, the events)."""
    text = str(text)
    for w in SECRET_WORDS: text = text.replace(w, '<id>')
    return text


def call(method, path, body=None):
    """(status, parsed JSON or {'_text': ...})."""
    r = requests.request(method, f'{BASE}/{path}', auth=AUTH, headers=H, json=body, timeout=60)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {'_text': r.text[:2000]}


def query(obj, body=None):
    code, d = call('POST', f'{obj}/query', body or {})
    return (d.get('result') or []) if code == 200 else [{'_error': code, **d}]


def licenses_used():
    lic = call('GET', f'Account/{ACCT}')[1].get('licensing') or {}
    return {k: v.get('used') for k, v in lic.items() if isinstance(v, dict) and v.get('used')}


TERMINAL = ('COMPLETE', 'COMPLETE_WARN', 'ERROR', 'ABORTED', 'DISCARDED')


def run_process(process_id, atom_id, alive=lambda: True):
    """Request one execution and wait for its record. Ends on a terminal status, or when alive() turns false
    (the container hosting the runtime has gone)."""
    t = time.time()
    code, d = call('POST', 'ExecutionRequest', {
        '@type': 'ExecutionRequest', 'atomId': atom_id, 'processId': process_id,
        'DynamicProcessProperties': {'@type': '', 'DynamicProcessProperty': []},
        'ProcessProperties': {'@type': '', 'ProcessProperty': []}})
    rid = d.get('requestId')
    if code != 200 or not rid:
        return {'status': f'REFUSED_{code}'}
    while True:
        code, rec = call('GET', f'ExecutionRecord/async/{rid}')
        row = (rec.get('result') or [{}])[0] if code == 200 else {}
        if row.get('status') in TERMINAL:
            return {'status': row['status'], 'wall_s': round(time.time() - t, 1), 'duration_ms': (row.get('executionDuration') or [None, None])[1],
                    'outbound_docs': row.get('outboundDocumentCount'), 'message': (row.get('message') or '')[:120] or None}
        if not alive():
            return {'status': 'HOST_ENDED_FIRST'}
        time.sleep(4)
