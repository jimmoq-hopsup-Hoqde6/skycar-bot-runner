# Offline workflow migration draft: activation locked

The workflow now checks out the reviewed runner controller at the immutable
workflow commit and the app input separately at the existing approved source SHA.
No app pin, app code, credentials, environment approval or protection is changed.
The run's trusted GitHub context is validated before generating an exact,
per-attempt fingerprint and printing a durable GitHub step summary. The static
fingerprint input is removed because the run ID is not known before dispatch.

The paid job is deliberately hard-disabled with `if: ${{ false }}`. An execute
input alone cannot activate it. A separate reviewed activation change is needed,
including exact preflight receipt review at the protected-environment approval.
This draft is not a runnable paid pilot or an independent watchdog.

## Independent recovery decision still required

Existing `skycar-agent-pilot` requires owner approval. Reusing it for a cleanup
job cannot promise unattended recovery. Do not remove its protection or copy its
key into repository secrets. A separate independently available cleanup authority
would require owner authorization for the specific identity/service, provider
project/session scope, allowed cancel/delete/read actions, credential storage,
and restrictions preventing task creation. We have not established that the
provider supports a key restricted to those operations, so do not claim it does.
If that isolation is unavailable, use a human-supervised recovery arrangement
with an explicitly available operator and verified billing cutoff; do not present
it as autonomous protection or a hard cleanup deadline.

A workflow_run/scheduled job is separate from a destroyed runner but can be
queued, cancelled or wait for approval. Without separately authorized access and
arming proof it is not an independently available supervisor. Metadata lookup
is eventually consistent, so an empty result remains unresolved and never
permits another creation. Exact deletion confirmation is not a billing receipt.

No provider access, paid call, permission change, merge or activation performed.
