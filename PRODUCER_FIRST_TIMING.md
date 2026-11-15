# One attended pilot: producer-first readiness wait

This changes timing only. Before any new live attempt, reconcile the historical
unresolved attempt and confirm the existing cost, key and environment approvals.

1. Dispatch the reviewed producer on main, attempt one, opting in. Complete its
   ordinary protected-environment approval first. It checks out inputs, installs
   the SDK, publishes its one-use claim and waits for recovery readiness.
2. Dispatch recovery targeting this exact producer run ID and same immutable
   workflow SHA. Its first job has no protected environment or OpenAI secret.
   It waits up to 300 seconds for the exact live `coding-task` job, successful
   `Publish one-use claim` step and in-progress `Execute one approved artifact-only
   task` step. Only this positive readiness result unlocks recovery's ordinary
   protected-environment approval. Approve that recovery promptly while the
   producer is still waiting. A queued job is not readiness.
3. After approval, recovery re-fetches the live producer and verifies the same
   immutable claim before its provider-read probe, and revalidates again before
   staging a receipt. Recovery publishes the receipt and begins its independent loop. Producer
   accepts only a uniquely identified live recovery, then downloads and validates
   the receipt and rechecks the complete existing authorization gate.
4. Remain present through execution and cleanup. An unresolved prior attempt,
   failed timing window or failed cleanup never authorizes another paid attempt.

The producer's recovery-readiness wait uses a monotonic 900-second deadline and
15-second polls (at most 60 discovery iterations). The separate secret-free
recovery job still waits at most 300 seconds for producer readiness.
An in-flight bounded GitHub read can finish after the deadline, but readiness
cannot be accepted after it. It waits only for an absent arming artifact or an
exact trusted live job with a queued/pending loop and publication either
in progress with no conclusion or completed successfully. Readiness requires
completed successful publication and an in-progress loop.
Authentication, identity, malformed, ambiguous and terminal-state errors fail
immediately. No provider client/session is created during this wait.

Receipt freshness stays 180 seconds; there is no refresh or automatic redispatch.
Fingerprint computation precedes the final complete gate to reduce the interval
between authorization and creation. The producer job timeout is 30 minutes to
accommodate setup, up to fifteen minutes of waiting and the existing 600-second task.
No settings, secrets, protections or creation scope change. This does not grant
new spending approval: the extra ten-minute runner allowance must fit the owner's
all-in budget before any live use.

## Recovery approval ordering safeguards

The secret-free wait reads only this repository's exact first-attempt run, jobs
and artifacts through the existing read-only GitHub token. It requires the
reviewed immutable SHA, main branch, manual producer workflow and live job.
It checks the claim's run/SHA, artifact ID, archive digest and sole file contents,
then re-fetches records after download. Its job ID, artifact ID and digest flow
to the protected job as a mandatory binding, not as authorization on their own.
Claim contents are never extracted or executed. API credentials are not loaded.

Missing/ambiguous jobs or published claims, malformed records, pagination,
authentication errors and terminal states fail closed. Only a positively
identified pending job or unfinished producer prerequisite can be polled.
If recovery starts before GitHub has listed the producer's job, it fails safely
rather than guessing a job identity. The deadline is checked after every probe;
an in-flight bounded read may finish later but cannot return late readiness.

The protected stage does not wait again or refresh the binding. Delayed approval,
producer cancellation, a replaced claim, or an expired producer wait prevents
receipt publication. The producer now allows fifteen minutes for this approval and startup sequence.
This reduces time pressure, but still requires attendance and fails closed at
the deadline. Receipt age is never extended or refreshed.
No observation guarantees future liveness; the producer's final complete gate,
180-second receipt freshness and one-use claim remain unchanged. A failed window
does not permit an automatic retry, new paid dispatch, or recreation of a session.
