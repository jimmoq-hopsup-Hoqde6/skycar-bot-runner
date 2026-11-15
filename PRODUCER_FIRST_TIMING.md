# One attended pilot: producer-first readiness wait

This changes timing only. Before any new live attempt, reconcile the historical
unresolved attempt and confirm the existing cost, key and environment approvals.

1. Dispatch the reviewed producer on main, attempt one, opting in. Complete its
   ordinary protected-environment approval first. It checks out inputs, installs
   the SDK, publishes its one-use claim and waits for recovery readiness.
2. While that wait is running, dispatch and normally approve recovery targeting
   this exact producer run ID and same immutable workflow SHA.
3. Recovery publishes the receipt and begins its independent loop. Producer
   accepts only a uniquely identified live recovery, then downloads and validates
   the receipt and rechecks the complete existing authorization gate.
4. Remain present through execution and cleanup. An unresolved prior attempt,
   failed timing window or failed cleanup never authorizes another paid attempt.

The readiness wait uses a monotonic 300-second deadline and five-second polls.
An in-flight bounded GitHub read can finish after the deadline, but readiness
cannot be accepted after it. It waits only for an absent arming artifact or an
exact trusted live job with a queued/pending loop and publication either
in progress with no conclusion or completed successfully. Readiness requires
completed successful publication and an in-progress loop.
Authentication, identity, malformed, ambiguous and terminal-state errors fail
immediately. No provider client/session is created during this wait.

Receipt freshness stays 180 seconds; there is no refresh or automatic redispatch.
Fingerprint computation precedes the final complete gate to reduce the interval
between authorization and creation. The producer job timeout is 20 minutes to
accommodate setup, up to five minutes of waiting and the existing 600-second task.
No settings, secrets, protections, spending approval or creation scope change.
