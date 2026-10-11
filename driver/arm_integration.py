"""Integration: a Boomi runtime that exists only for this job.

Mints a single-use installer token, starts Boomi's official runtime container on this runner, waits until the
platform shows it ONLINE, runs a deployed process on it (must COMPLETE and return a document) and one built to
fail (must ERROR), then stops the container, deletes the runtime and confirms the account is back to its
starting counts. Every wait ends on a state: readiness answers, the platform shows ONLINE, the execution reaches
a terminal status, or the container is no longer running.
"""
import os, pathlib, subprocess, sys, time
from datetime import datetime, timezone
from boomi_api import IDS, call, licenses_used, query, run_process
from demo_report import finish, step
from sweep_runtimes import PREFIX, sweep

NAME = PREFIX + datetime.now(timezone.utc).strftime('%Y%m%dt%H%M%Sz') + '-' + os.environ.get('GITHUB_RUN_ID', 'local')[-6:]


def sh(*a): return subprocess.run(a, capture_output=True, text=True)
def container(): return sh('docker', 'inspect', '-f', '{{.State.Status}}', 'atom').stdout.strip() or 'gone'
def test_runtimes(): return [a for a in query('Atom') if str(a.get('name', '')).startswith(PREFIX)]


def main():
    cpu = os.cpu_count(); mem = round(os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / 2**30, 1)
    step('runner', 'GitHub gave this job a runner', cpus=cpu, memory_gb=mem)
    swept, _ = sweep()
    before = (len(test_runtimes()), licenses_used())
    step('baseline', 'Read the account before touching it', test_runtimes=before[0], licenses_in_use=sum(before[1].values()), leftovers_removed=len(swept))

    code, tok = call('POST', 'InstallerToken', {'installType': 'ATOM', 'durationMinutes': 30})
    if code != 200 or not tok.get('token'):
        return step('token', 'Asked Boomi for a single-use installer token', 'failed', http=code) and False
    print(f"::add-mask::{tok['token']}")
    step('token', 'Boomi issued a single-use installer token', valid_minutes=30)

    work = pathlib.Path(os.environ.get('RUNNER_TEMP', '/tmp')) / 'boomi'; work.mkdir(parents=True, exist_ok=True); os.chmod(work, 0o777)
    t = time.time()
    r = subprocess.run(['docker', 'run', '-d', '--name', 'atom', '-h', NAME, '-e', 'INSTALL_TOKEN', '-e', f'BOOMI_ATOMNAME={NAME}', '-e', f'ATOM_LOCALHOSTID={NAME}',
                        '-e', f"BOOMI_ENVIRONMENTID={IDS['ci_env']}", '-p', '9090:9090', '-v', f'{work}:/mnt/boomi:Z', 'boomi/atom:release'],
                       env=dict(os.environ, INSTALL_TOKEN=tok['token']), capture_output=True, text=True)
    if r.returncode:
        return step('container', "Started Boomi's runtime container", 'failed', error=r.stderr[:160]) and False
    step('container', "Started Boomi's official runtime container (boomi/atom)", pulled_and_started_s=round(time.time() - t, 1))

    while True:      # ends when readiness answers 200, or the container is no longer running
        if sh('curl', '-s', '-o', '/dev/null', '-m', '5', '-w', '%{http_code}', 'http://localhost:9090/_admin/readiness').stdout == '200': break
        if container() != 'running':
            return step('ready', 'The runtime installed itself and answered its health check', 'failed', container=container()) and False
        time.sleep(3)
    step('ready', 'The runtime installed itself and answered its health check', seconds_after_start=round(time.time() - t, 1))

    atom = None
    while True:      # ends when the platform shows this runtime ONLINE, or the container is no longer running
        mine = [a for a in query('Atom') if a.get('name') == NAME and a.get('status') == 'ONLINE']
        if mine: atom = mine[0]; break
        if container() != 'running':
            return step('online', 'Boomi shows the runtime ONLINE', 'failed', container=container()) and False
        time.sleep(3)
    step('online', 'Boomi shows the runtime ONLINE, attached to a test environment', seconds_after_start=round(time.time() - t, 1), runtime_name=NAME, licenses_in_use=sum(licenses_used().values()))

    alive = lambda: container() == 'running'
    e = run_process(IDS['process_keyless'], atom['id'], alive)
    good = e['status'] == 'COMPLETE' and (e.get('outbound_docs') or 0) >= 1
    step('process', 'Ran a deployed process on it: it fetched a public page and returned the document', 'done' if good else 'failed',
         boomi_status=e['status'], boomi_duration_ms=e.get('duration_ms'), documents_out=e.get('outbound_docs'))
    f = run_process(IDS['process_failing'], atom['id'], alive)
    bad = f['status'] == 'ERROR'
    step('canary', 'Ran a process built to fail: Boomi reported the error, so a pass means something', 'done' if bad else 'failed', boomi_status=f['status'])
    mem_now = sh('docker', 'stats', '--no-stream', '--format', '{{.MemUsage}}', 'atom').stdout.split('/')[0].strip()
    step('memory', 'Measured the runtime while it was up', runtime_memory=mem_now)
    return good and bad


def teardown(before_known=True):
    subprocess.run(['docker', 'stop', '-t', '60', 'atom'], capture_output=True)
    deleted, refused = sweep()
    left = test_runtimes()
    step('deleted', 'Stopped the container and deleted the runtime from Boomi', 'done' if not left and not refused else 'failed', deleted=len(deleted), refused=len(refused))
    ok = step('clean', 'Nothing left behind: the account is back where it started', 'done' if not left else 'failed', test_runtimes=len(left), licenses_in_use=sum(licenses_used().values()))
    return ok and not refused


if __name__ == '__main__':
    ok = False
    try:
        ok = bool(main())
    except Exception as e:      # a bug in this script is a failed run on the record, never a silent one
        step('crashed', 'The script stopped on an error', 'failed', error=f'{type(e).__name__}: {e}'[:160])
    finally:
        clean = teardown()
    ok = ok and clean
    finish(ok, 'A runtime booted on a GitHub runner, ran a process and was deleted' if ok else 'The run did not hold: see the failed step')
    sys.exit(0 if ok else 1)
