"""Flow: run a published Flow app headlessly from the runner, the way a visitor's browser would.

No credential is used: the app is public, so the runner sends only what the public player sends. It starts the
flow, lands on the first page, presses the app's one button, and checks the next page loaded rows. Those rows
come from Boomi Data Integration, read live through a Boomi Integration listener, so one press exercises three
Boomi products. Nothing is created or removed, and no credits are spent.

Then a real browser on the runner opens the same app, presses the same button and saves a picture of the page it
lands on, so the run leaves behind what the product looked like and not only numbers. The workflow commits the
picture beside the ledger row. A picture that could not be taken is reported as such and never decides the run.
"""
import base64, hashlib, json, os, pathlib, sys, time, urllib.error, urllib.request
from demo_report import finish, step

API = 'https://us.flow-prod.boomi.com'
HDR = {'manywhotenant': os.environ['FLOW_TENANT'], 'Content-Type': 'application/json', 'Accept': 'application/json'}
BUTTON, PAGE = 'Ask BDI for its pipelines', 'Pipelines'
SHOTS = pathlib.Path(__file__).resolve().parent.parent / 'docs' / 'shots' / 'flow'


def picture(run_id, must_show):
    """Open the public app in headless Chrome, press its button, wait until `must_show` (a pipeline name the API
    run just read) is on the page, and save a JPEG. Returns the facts to report."""
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    opts = webdriver.ChromeOptions()
    for a in ('--headless=new', '--window-size=1200,1000', '--no-sandbox', '--hide-scrollbars'): opts.add_argument(a)
    d = webdriver.Chrome(options=opts)
    try:
        d.get(f"{API}/{os.environ['FLOW_TENANT']}/play/kumori?flow-id={os.environ['FLOW_ID']}")
        button = lambda _: next((b for b in d.find_elements(By.XPATH, "//button | //a") if BUTTON in (b.text or '')), None)
        WebDriverWait(d, 45).until(button).click()
        WebDriverWait(d, 45).until(lambda _: must_show in d.find_element(By.TAG_NAME, 'body').text)
        jpeg = base64.b64decode(d.execute_cdp_cmd('Page.captureScreenshot', {'format': 'jpeg', 'quality': 72})['data'])
    finally:
        d.quit()
    SHOTS.mkdir(parents=True, exist_ok=True)
    (SHOTS / f'{run_id}.jpg').write_bytes(jpeg)
    return {'picture': f'docs/shots/flow/{run_id}.jpg', 'picture_kb': round(len(jpeg) / 1024), 'picture_sha256': hashlib.sha256(jpeg).hexdigest()[:16]}


def post(path, body):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), headers=HDR, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=60) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, {}


def page_of(d): return (d.get('mapElementInvokeResponses') or [{}])[0]


def main():
    t = time.time()
    code, run = post('/api/run/1/state', {'id': os.environ['FLOW_ID']})
    if not step('start', 'Started the Flow app with no login, as a browser would', 'done' if code == 200 else 'failed', http=code): return False
    sid = run['stateId']
    def go(prev, outcome=None):
        return post(f'/api/run/1/state/{sid}', {'stateId': sid, 'stateToken': prev['stateToken'], 'currentMapElementId': prev.get('currentMapElementId'),
                                                'invokeType': 'FORWARD', 'mapElementInvokeRequest': {'selectedOutcomeId': outcome, 'pageRequest': {'pageComponentInputResponses': []}}})
    code, first = go(run)
    buttons = [o['label'] for o in page_of(first).get('outcomeResponses') or []]
    if not step('page', 'Landed on its first page and found the button', 'done' if code == 200 and BUTTON in buttons else 'failed', page=page_of(first).get('developerName'), buttons=len(buttons)): return False
    oc = next(o['id'] for o in page_of(first)['outcomeResponses'] if o['label'] == BUTTON)
    t_press = time.time()
    code, nxt = go(first, oc)
    landed = page_of(nxt).get('developerName')
    if not step('press', 'Pressed the button: Flow called Boomi Integration, which asked Boomi Data Integration', 'done' if code == 200 and landed == PAGE else 'failed',
                landed_on=landed, round_trip_ms=round((time.time() - t_press) * 1000)): return False
    rows = [o for d in (page_of(nxt).get('pageResponse') or {}).get('pageComponentDataResponses') or [] for o in d.get('objectData') or []]
    names = sorted(next((p['contentValue'] for p in r['properties'] if p['developerName'] == 'name'), '?') for r in rows)
    ok = step('rows', 'The page loaded live rows (zero rows would be a failure, not a pass)', 'done' if rows else 'failed', pipelines=len(rows), first=names[0][:40] if names else None)
    if ok:
        from demo_report import RUN_ID
        try: step('picture', 'A browser on the runner opened the same app, pressed the button and saved what it saw', **picture(RUN_ID, names[0]))
        except Exception as e: step('picture', 'A browser on the runner tried to save a picture of the app and could not', picture=f'not taken: {type(e).__name__}')
    return ok and step('clean', 'Nothing was created, so there is nothing to remove', total_seconds=round(time.time() - t, 1))


if __name__ == '__main__':
    ok = False
    try: ok = bool(main())
    except Exception as e: step('crashed', 'The script stopped on an error', 'failed', error=f'{type(e).__name__}: {e}'[:160])
    finally: finish(ok, 'A runner ran a live Flow app end to end: Flow, Integration and Data Integration answered' if ok else 'The run did not hold: see the failed step')
    sys.exit(0 if ok else 1)
