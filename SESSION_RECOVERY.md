# Recovery draft: not an installed watchdog

`recover_pilot_session.recover()` is a dry-by-default library primitive for an
independent supervisor. It creates no session, sends no task, discovers no sessions,
and changes no existing workflow. Explicit execution retrieves one trusted session,
checks exact reviewed task/repository/commit metadata, then cancels and attempts
bounded deletion. Only an exact positive deletion response is called confirmed.
404, ambiguous responses, transport errors and exhausted conflicts need reconciliation.
This is not a billing receipt or a guarantee that charges have stopped.

## Current failure windows (NOT FIXED by this draft)

The live controller writes the session ID to its local state.json after create.
The workflow uploads artifacts only after the controller finishes. SIGKILL, host
loss or workflow termination can prevent that upload. Atomic local rename does not
make data durable outside the runner. A server-side creation followed by response
loss can leave a session whose ID was never received. Do not blindly recreate it.
The model artifact is untrusted and is not an acceptable recovery receipt.

## Required integration before calling this an independent watchdog

1. Provision an independently hosted supervisor and durable trusted receipt store.
   Its credentials must remain outside generated-code sandboxes and have the
   correct project scope. Do not place any key in the receipt or public logs.
2. Persist a unique approved attempt identity BEFORE create and include it in
   session metadata; use documented idempotency only if supported for creation.
3. Immediately persist the returned session ID externally and require supervisor
   acknowledgement BEFORE submitting the model task. Fail closed if this fails.
4. Supervisor must reconcile a lost create response via a verified provider lookup
   bound to the unique attempt; absent that, stop and investigate, never guess.
5. Supervisor owns the deadline even if the GitHub runner dies. It uses a trusted
   receipt to cancel/delete the exact session; preserve results durably, alert on
   any unconfirmed outcome, reconcile usage, and forbid the next paid dispatch.
6. Test supervisor termination/restart and runner SIGKILL before any paid attempt.

The current primitive validates the original pilot metadata exactly; adding a new
attempt field requires an explicit reviewed update to both producer and verifier.
No durable store, supervisor service, live credentials, paid call, schedule, or
workflow wiring is included here. Existing hard-limit/headroom requirements remain.

## Offline verification

`python3 -m unittest discover -s tests/autonomy -p 'test_recover_pilot_session.py' -v`
uses mocks only and covers offline default, scope/identity rejection, no-ID fail
closed, cancellation failure, bounded 409 retry, non-409 no retry, false 404 and
ambiguous deletion. SDK/server integration has not been verified for this primitive.
