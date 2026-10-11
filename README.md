# boomi-on-actions

A Boomi runtime that exists only while a pipeline runs.

Each run of the workflow here starts Boomi's official runtime container (`boomi/atom`) on a GitHub-hosted runner,
waits until the Boomi platform shows it ONLINE, runs a deployed process on it, deletes the runtime, and checks the
account is back where it started. Nothing is installed anywhere else: no VM, no cloud account, no always-on server.

**Unofficial.** Not made, reviewed or endorsed by Boomi or GitHub. By Kumori (https://kumori.ai).

## Watch it, or start one
- **Start a run and watch it live:** https://kumori.ai/demo/boomi
- **Every run ever made:** [`docs/ledger/runs.jsonl`](docs/ledger/runs.jsonl), one row per run, committed by the run itself
- **The job logs:** the Actions tab of this repository

## What a run proves, by arm
| Arm | What the run does | What it stands up and removes |
|---|---|---|
| `integration` | Mints a single-use installer token, boots a runtime on the runner, runs one process that must complete and one built to fail, deletes the runtime | A real Boomi runtime |
| `edi` | Creates an X12 trading partner through the Platform API, reads it, finds it, deletes it | A component; the runner is only the API client |

## What this is for, and what it is not
It is a way to build and test against a real Boomi runtime with nothing to host: the same cycle a pull request
check would run before a change merges. It is not a place to run production. A runner takes no inbound traffic,
a job ends, and the test account behind these runs holds no production data or credentials.

## How it is kept honest
- Every wait ends on a state (the runtime is ONLINE, the execution reached a terminal status), never on a timer.
- Each Integration run includes a process built to fail. Boomi must report the error, or the run fails.
- Each Integration run reports what Boomi itself recorded: the id, version and install time Boomi gave the runtime, and the id and time of each execution.
- Each Flow run ends with a real browser on the runner opening the app, pressing its button and committing a picture of the page to `docs/shots/flow/`, named for the run.
- Teardown runs even when a run crashes or is cancelled, and the run fails if a test runtime is left behind.
- Account, environment and process ids come from repository secrets and are masked in every log line.
- One run at a time, across all arms.

## Layout
`driver/` the scripts a run executes · `.github/workflows/demo.yml` the one workflow · `docs/ledger/` the record
