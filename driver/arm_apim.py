"""API Management: read the control plane through GraphQL with a five-minute token.

Trades the Platform API token for a JWT that lives five minutes, asks the GraphQL endpoint what it offers, and
reads the account's environments through it. Read-only: nothing is created, changed or removed.
"""
import sys, time
import requests
from boomi_api import ACCT, AUTH
from demo_report import finish, step


def main():
    t = time.time()
    j = requests.get(f'https://api.boomi.com/auth/jwt/generate/{ACCT}', auth=AUTH, timeout=30)
    if not step('token', 'Traded the API token for a five-minute JWT', 'done' if j.status_code == 200 and j.text.count('.') == 2 else 'failed', http=j.status_code, lives_minutes=5): return False
    head = {'Authorization': 'Bearer ' + j.text.strip(), 'Content-Type': 'application/json'}
    def ask(q): return requests.post('https://api.boomi.com/graphql', headers=head, json={'query': q}, timeout=60)
    r = ask('{ __schema { queryType { fields { name } } mutationType { fields { name } } } }')
    sch = ((r.json().get('data') or {}).get('__schema') or {}) if r.status_code == 200 else {}
    nq, nm = len((sch.get('queryType') or {}).get('fields') or []), len((sch.get('mutationType') or {}).get('fields') or [])
    if not step('schema', 'Asked GraphQL what it offers', 'done' if nq and nm else 'failed', http=r.status_code, queries=nq, mutations=nm): return False
    r = ask('{ account { status } environments { __typename } }')
    d = r.json().get('data') or {}
    ok = step('read', 'Read the account and its environments through GraphQL', 'done' if d.get('account') and d.get('environments') is not None else 'failed',
              account_status=(d.get('account') or {}).get('status'), environments=len(d.get('environments') or []))
    r = requests.post('https://api.boomi.com/graphql', headers={'Content-Type': 'application/json'}, json={'query': '{ account { status } }'}, timeout=60)
    refused = r.status_code in (401, 403) or bool((r.json() if r.headers.get('content-type', '').startswith('application/json') else {}).get('errors'))
    ok &= step('canary', 'Asked again with no token: refused, so the first answers needed it', 'done' if refused else 'failed', http=r.status_code)
    return ok and step('clean', 'Nothing was created, so there is nothing to remove', total_seconds=round(time.time() - t, 1))


if __name__ == '__main__':
    ok = False
    try: ok = bool(main())
    except Exception as e: step('crashed', 'The script stopped on an error', 'failed', error=f'{type(e).__name__}: {e}'[:160])
    finally: finish(ok, 'A runner read API Management through GraphQL with a five-minute token' if ok else 'The run did not hold: see the failed step')
    sys.exit(0 if ok else 1)
