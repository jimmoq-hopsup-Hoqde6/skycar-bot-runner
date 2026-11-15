# Producer integration candidate, not activated

The runner controller now binds the approved source request to seven-field run
metadata. Execute rejects missing/tampered identity before creating a session.
The request carries identity at creation, so an independent supervisor can recover
lost-create outcomes using trusted GitHub run data through reconcile(), not the
old three-field recover(). Local state stores the same metadata before creation;
local state alone is not durable across host loss.

Fingerprint now binds run ID, first run attempt and immutable workflow SHA in
addition to source bytes, task, model, network and session limit. Different runs
need different fingerprints. The old static fingerprint does not approve these
new requests. Preflight accepts --run-id, --run-attempt and --workflow-sha together.
These values must come from independently verified GitHub context, not generated
artifacts or arbitrary dispatch inputs. Identity validation is not authentication.

Cleanup requires exact session ID and deleted is True. A nonthrowing response is
not sufficient. Artifact review was updated atomically to require
'deletion_confirmed'; old 'deletion_requested' evidence is rejected. A new
producer-to-review regression checks this contract without executing generated code.
Deletion confirmation is not an authoritative bill or a claim of zero later charges.

## Still required before live execution

Existing one-coding-bot.yml checks out the old APP controller, not this runner
copy. No workflow, source pin, app branch or main branch is changed in this draft.
A separately reviewed workflow migration must select this producer controller,
keep the app input pinned, derive trusted run identity, and expose its exact
per-attempt fingerprint for protected environment approval. No reusable live
approval fingerprint is asserted by this draft.

An independent supervisor must be armed before creation and have approved access
to the correct project. Current protected-environment owner approval can also
block cleanup jobs; GitHub queue/scheduling latency is not a hard deadline. No
credential scope changes, bypass or new paid service is proposed. Durable cleanup
result storage, lost-create visibility/restart tests and actual provider cost
controls remain unverified. Keep the A$100 week-one all-in cap and US$30 first-pilot
sub-cap, including FX and fees. No paid dispatch is authorized by merging code.

79 offline tests pass with pinned openai==3.49.0, no skips. Mock transport verifies
the seven-field creation payload. Other tests cover legacy request rejection,
fingerprint variation, creation-timeout evidence, strict deletion confirmation,
and successful producer-to-review output. No real key or live API calls used.
