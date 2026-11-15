# Durable attempt recovery draft, not deployed

A GitHub run already has durable repository, run ID, run attempt and head SHA
before a provider session is created. A separate supervisor can reconstruct that
identity from the authenticated GitHub run record even if the runner loses every
local file. This avoids relying solely on a session-ID artifact uploaded at exit.

The proposed producer must include `attempt_metadata(run_id, 1, workflow_sha)` in
its session creation request. The existing producer DOES NOT yet do this. Its
fingerprint would change and needs fresh review. Do not use this new lookup on old
sessions or infer an attempt ID from generated model output.

The pinned SDK supports exact metadata filtering on sessions.list. Its source
explicitly warns that new sessions/metadata updates may take time to appear.
`reconcile()` therefore treats no match as unresolved, never proof of no creation
or permission to create again. More than one result, more pages, scope mismatches,
API errors, and ambiguous deletion also require reconciliation. An exact match is
retrieved again before cancellation/deletion; no model input is ever submitted.
It limits SDK retries to zero and each transport phase to 20 seconds. This is not
an overall wall-clock deadline; an external supervisor must enforce its lifetime.

## Existing-infrastructure route and blockers

A separate GitHub workflow_run completion workflow could reconstruct the original
run identity and call reconciliation after failure/cancellation/timeout. It must
verify the exact source repo, workflow identity, head SHA, main branch, event and
run attempt from GitHub, and check out its own pinned reviewed cleanup source,
never the originating run's arbitrary source or model artifact. A scheduled sweep
would be needed for missed/delayed completion events and eventual consistency.

However both would require the protected environment key. Existing owner-review
protection means that independent cleanup can itself wait for a human. Removing
that protection or copying the key into a less protected scope is NOT proposed.
GitHub queue/scheduler latency also cannot guarantee the ten-minute deadline.
Thus no unattended operational watchdog can be claimed with just these modules.

Before enabling: establish approved independent supervisor execution/credential
access and immutable run evidence; integrate producer metadata and new fingerprint;
write and independently review trigger/run-origin validation; test lost create
response, runner kill, supervisor restart, delayed visibility and cleanup failure;
reconcile usage and preserve the weekly AUD budget and first-pilot USD sub-cap.
No additional service, credentials, permissions, workflow or paid run is installed
by this draft. Provider-side budget headroom remains mandatory.

## Verification

Unit tests simulate identity loss, delayed visibility, duplicates, pagination,
identity mismatch and delete-response loss. A pinned openai==3.49.0 MockTransport
test verifies actual metadata query encoding and exact GET/GET/cancel/DELETE flow
without contacting OpenAI. These are offline tests, not proof of server behavior.
