# One coding bot candidate
`One bounded coding bot` is a proposed manual workflow for the existing reviewed
queue-input-validation task at app commit `f10a36fe98961dc1dcfbace37d9323752e1f3ffe`.
It is separate from the nine report sessions. Its default invocation runs only
credential-free preflight. Paid execution requires explicit opt-in, the exact
preflight fingerprint and the protected environment's owner approval on main.
This PR alone does not authorize a live run. Confirm a usable environment-scoped key,
provider access and an approved all-in spending bound before any live invocation.
The controller requests a US$1 session limit; this is not a total billing cap.
A successful paid task produces a review patch and evidence, NOT a tested or
published app change. Generated code must undergo independent inspection and
credential-free isolated testing before a separate draft PR is considered.
There is no scheduler, automatic retry, merge or application deployment.



## Required operator checks before any paid dispatch

- Store SKYCAR_PILOT_OPENAI_API_KEY only in the protected skycar-agent-pilot environment. Verify this exact name is absent from repository and organization secrets. GitHub secret expressions do not attest their scope; the distinct name avoids the existing generic OPENAI_API_KEY fallback but does not independently enforce environment-only storage.
- Verify main-only environment deployment rules, required independent reviewer and no self-review/bypass. No protection changes are included in this PR.
- Reconcile all earlier coding runs and provider session IDs before approval. run_attempt == 1 rejects reruns, but a new dispatch has a new run ID and is NOT prevented by that check. Concurrency serializes work; it is not a single-use authorization ledger. Approve exactly one run and reject later dispatches until fresh authorization.
- Confirm provider session pricing and sandbox/runner charges fit the approved all-in cap. The US$1 session limit and 15-minute GitHub job timeout do not prove total cost or remote cleanup after hard termination. Do not dispatch while these costs or cleanup are uncertain.
- Record GitHub run ID, request fingerprint, provider session/turn IDs, timestamps, cleanup outcome and provider usage/billing evidence. Current artifacts record execution IDs/status, not authoritative total billed cost. Missing/lagged usage must remain unknown, never reported as zero. Reconcile before another task.

A durable atomic, single-use authorization record and provider usage reconciliation are still needed before unattended repeated execution. This candidate remains supervised and default-off.
