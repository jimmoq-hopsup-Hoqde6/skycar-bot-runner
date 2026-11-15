# One supervised pilot activation REVIEW candidate

This branch targets runner main as one aggregate review of the stacked recovery
work. Existing drafts and app branches remain untouched. This document supersedes
earlier historical draft notes about literal-false job conditions in this branch.
Nothing has been merged or dispatched by preparing this candidate.

Both workflows are manual-only, default opt-out, repository/main/first-attempt
restricted, and still require normal skycar-agent-pilot environment approval.
No schedule, auto-approval, admin bypass, auto-top-up, automatic retry or app
publication. One explicitly approved task, 100 US cents configured session limit,
network-disabled sandbox, no credentials passed into generated-code environment.

## Operator sequence after normal review and merge

1. Verify the correct funded provider project/key and enforced temporary US$5
   project limit, with room inside the approved US$30 pilot and A$100 week-one
   totals. Do not use budget alerts/prepaid balance as an instantaneous cap.
2. Dispatch One bounded coding bot on main with execute_paid_task=true. Review
   exact preflight receipt and fingerprint; leave coding-task awaiting approval.
3. Dispatch Supervised pilot recovery on the SAME main SHA, target exact producer
   run ID, arm_supervised_recovery=true. Approve its normal environment request.
4. Observe completed Publish arming receipt and running Bounded recovery loop.
   Approve producer promptly; its checkout/install/gate must finish within the
   180-second receipt freshness window or it stops without creating a session.
5. Do not rerun or create another producer on a failure. Inspect retained evidence
   and reconcile any unknown session before requesting another approval.
6. Review generated artifact and test separately in a credential-free environment.
   No app merge/deploy is authorized by the pilot. Source remains the old approved
   app pin; generated patch is not automatically applicable to newer app main.

A human remains present through cleanup. Successful producer deletion may leave
recovery's later metadata search empty/unresolved; inspect producer's exact
confirmed-deletion evidence rather than treating empty search as success. No hard
cleanup deadline or final-charge guarantee. Current independent/mock testing is
not proof the real provider/key/network/artifact handshake will work.

120 offline tests pass, including documented job payload compatibility. Exact
head and the aggregate candidate needs independent review before normal merge.
