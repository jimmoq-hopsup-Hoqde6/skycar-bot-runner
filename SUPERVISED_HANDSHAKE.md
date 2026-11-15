# Supervised recovery handshake

The manual, opt-in workflows wire a single supervised pilot, not nine autonomous
bots. The current operator sequence is in [PRODUCER_FIRST_TIMING.md](PRODUCER_FIRST_TIMING.md).
This code and its offline tests do not authorize paid execution.

## Concrete path

1. Producer preflight emits the exact run-bound request fingerprint and waits for
   normal protected-environment approval. App input remains at the approved pin.
2. Approve the producer's existing protected environment first. It completes
   checkout/install, uploads its claim and waits up to five minutes for recovery.
   Separately dispatch recovery for that producer ID and the same workflow SHA.
3. Recovery's secret-free job waits for exact live producer execution and verifies
   its immutable claim. Only then can the human approve recovery's protected job.
   After approval recovery revalidates the same producer/claim before its provider
   read and again before staging a digest-bound arming receipt. No readiness means
   no receipt. The distinct concurrency groups allow both workflows to run.
4. Producer's fixed-name v4 one-use claim uses overwrite=false. It verifies
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

Offline tests use the pinned SDK and mocked network/provider behavior. They do
not establish live service availability. Unsupported artifact storage hosts, pagination, ambiguity,
stale receipts and digest mismatches fail closed.

Normal merge review preserves explicit opt-in/main/first-attempt/approval
safeguards. Two ordinary environment approvals and attended supervision remain
required. Merging an ordering fix does not authorize a new paid execution.
