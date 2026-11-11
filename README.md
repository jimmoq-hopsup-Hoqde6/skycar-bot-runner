# Skycar bot runner

Nine role sessions with explicit handoffs: project-manager, product, ux-ui, mobile,
backend, ai-specialist, qa, security and release.

## Current scope

The manual **Nine-role bootstrap** workflow starts separate hosted agent sessions
in sequence. Each receives the captured Skycar issue queue, runner source and
previous role reports. Each returns a validated Markdown report artifact.
QA and Security have separate sessions. Their reports are advisory, not release
approval. This first cycle does not modify the application or open pull requests.

The existing two-file coding pilot from skycar-site PR #95 is preserved in
`scripts/autonomy/bounded_coding_pilot.py`, with its original tests. It is not
automatically invoked by the nine-role reporting cycle.

## Activate the first cycle

1. Add the already-authorized Skycar key to this repository's Actions secrets as
   `OPENAI_API_KEY`. Never commit it or post it in an issue or chat.
2. Check **Runner offline tests** is green on the exact main commit.
3. Open Actions → Nine-role bootstrap → Run workflow on main.
4. Inspect `nine-role-evidence-RUN_ID`, particularly `summary.json` and each role's
   `state.json`. Count actual completed sessions, not configured roles.

No live run is implied by installing these files. Provider access, billing and
key validity are established only by the first live run. The current snapshot is
dated 2026-11-11 and is not a current-state audit of the application.

## Bounds and recovery

- Hosted session limit: 100 US cents, confirmed by API before task submission.
- Nine sessions maximum per invocation, so at most US$9 in session limits.
- One active workflow; one agent session at a time; 10-minute session deadline.
- Sandbox network disabled; no credentials, repository writes or external tools.
- Controller has a read-only GitHub token, not passed to the hosted agent.
- Failure stops the cycle. Automatic retries and workflow reruns are blocked.
- Evidence persists on failure; reconcile session/cleanup state before a new run.
- Cancel the workflow to stop it; cancellation requests session cleanup. Check
  evidence for pending cleanup. An unknown creation outcome requires reconciliation.
- No schedule, monthly spend ledger, automatic merge, deployment or release.
  Do not enable recurring paid cycles until cumulative budget enforcement and
  independent review of this controller are complete.

## Verification

`python3 -m pip install -r scripts/autonomy/requirements-pilot.txt`

`python3 -m unittest discover -s tests/autonomy -p 'test_*.py' -v`

`python3 scripts/autonomy/team_bootstrap.py` prints offline preflight metadata
from a clean committed checkout without accessing an API key.

Next development milestone: validate the live nine-role bootstrap, run the
bounded coding pilot, independently test its generated artifact, then publish a
draft PR. These steps must not be reported as complete from passing mock tests.
