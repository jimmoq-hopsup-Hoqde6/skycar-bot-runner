# Supervised recovery candidate: wired, not activated

Both workflow jobs remain hard-disabled. This draft wires a single supervised
pilot, not nine autonomous bots. No real credentials, paid calls, settings changes
or main merges were used to develop or test it.

## Concrete path

1. Producer preflight emits the exact run-bound request fingerprint and waits for
   normal protected-environment approval. App input remains at the approved pin.
2. Separately dispatch recovery for that producer ID and approve its existing
   protected environment normally. The distinct concurrency group allows both
   workflows to run concurrently. Recovery validates trusted GitHub run identity,
   probes provider read access, stages and uploads a digest-bound arming receipt.
3. Only after the recovery loop is visibly running should the human approve the
   producer. Checkout/install and verification must finish within the receipt's
   180-second freshness window; otherwise producer stops without creation.
4. Producer uploads a fixed-name v4 one-use claim with overwrite=false. It verifies
   that exact returned artifact ID, discovers one same-SHA recovery, downloads its
   bounded receipt archive without forwarding GitHub credentials to blob storage,
   checks digest/identity, and re-fetches live recovery job/step proof.
5. Producer creates one session only after all gates and the exact fingerprint
   pass. The claim is per-run, not a cross-run spending ledger. Reruns are rejected;
   another run needs another normal approval. There is no automatic rearming.
6. Recovery waits until the maximum start window plus 600-second task bound plus
   30 seconds, then reconciles at most six times. It allows terminal producer
   status during cleanup identity validation, so cancellation/failure cannot
   skip cleanup. Unknown creation/deletion/persistence never permits recreation.

## Human and billing requirements

Keep a human available through completion and reconciliation. The existing
protected environment may supply its key separately to each approved workflow;
no protection bypass or repository-level key copy is needed. The provider read
probe does not prove cancel/delete authority: existing project key permissions
must be checked independently. No delete-only permission is assumed.

If producer already deleted its session, recovery's empty metadata search stays
unresolved. The human must inspect the producer's confirmed-deletion evidence;
empty search is not proof of cleanup. Metadata indexing is eventually consistent.
Recovery can die immediately after liveness verification; API calls can finish
past the polling deadline. This is not a hard cleanup-deadline guarantee.

Verify enforced project spend control and remaining A$100 week-one / US$30 pilot
allowance before activation. Prepaid balance and budget alerts alone are not
instantaneous cutoffs. Deletion confirmation is not a final billing receipt.

## Verification and activation boundary

119 distinct offline tests pass with pinned SDK, independently rerun. Network
and provider behavior are mocked. Both YAML files parse and all shell blocks
pass bash -n. No upload/download handshake or live controller has been exercised
against GitHub/OpenAI. Unsupported artifact storage hosts, pagination, ambiguity,
stale receipts and digest mismatches fail closed.

Normal merge review and a separately reviewed activation change must restore
explicit opt-in/main/first-attempt/approval safeguards. Never replace false with
true alone. Two ordinary environment approvals and attended supervision are
still required; this draft does not authorize paid execution.
