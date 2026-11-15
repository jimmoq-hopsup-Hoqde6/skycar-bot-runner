# Local review proposal: reduce second-approval time pressure

Base: b7fd10827445c29561bcfc7cd693f5db3eff995b. Not published or activated.

## Recommendation
Use a fixed 15-minute pre-arming producer wait, with 15-second polling and a
30-minute producer job cap. This is not a 15-minute receipt. Keep the existing
180-second receipt freshness, 600-second task, 1200-second recovery lease,
independent recovery, exact run/attempt/SHA/job/claim binding and final gate.
No automatic retry, receipt refresh, provider creation during waiting, or
approval bypass. Both human protected-environment approvals remain mandatory.

The recovery approval must complete early enough to install the SDK, validate
producer identity, probe provider state, publish the receipt and start its loop.
The bound is not a promise of fifteen whole minutes for the human alone.

## Resource/security trade-off
At most 60 producer discovery iterations, as before, but up to ten additional
runner minutes. Each iteration can include multiple bounded GitHub reads.
Existing GitHub and provider credentials remain scoped as before, but the
producer execution step currently receives its provider key before waiting;
this proposal increases that credential-bearing step's potential residency.
No provider client is constructed by the producer until after the final gate.
Do not describe this as secret-free waiting or as a budget-neutral change.
Confirm the runner-minute allowance fits the all-in approval before live use.

## Alternatives
1. Keep current code and offer a clear approval link immediately when recovery
   becomes eligible. Lowest code risk, but still fragile for a phone user.
2. This bounded extension: smallest auditable improvement; two approvals remain.
3. Future two-phase prepare/arm protocol: wait for human approvals before minting
   execution freshness. Separate the credential-free waiting step from the
   credential-bearing execution step, bind both workflows and the one-use claim,
   independently revalidate both live jobs, then mint one fresh receipt. Requires
   redesigned exact-step identity checks, cancellation/late-approval race tests,
   and approval semantics review. Not safe as a quick workflow-label edit.

Never use unbounded waiting, automatic re-dispatch, cached approval of another
run, or refresh of an expired receipt to solve the UX issue.

## Required before deployment
Independent review of exact patch, all CI at that SHA, explicit publication and
live-use scope, current failed-attempt reconciliation, and all-in runner budget.
No live settings, approvals, dispatches, paid calls or hosted writes were made.
