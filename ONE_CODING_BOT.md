# One coding bot candidate
`One bounded coding bot` is a proposed manual workflow for the existing reviewed
queue-input-validation task at app commit `f10a36fe98961dc1dcfbace37d9323752e1f3ffe`.
It is separate from the nine report sessions. Its default invocation runs only
credential-free preflight. Paid execution requires explicit opt-in, the exact
preflight fingerprint and the protected environment's owner approval on main.
This PR alone does not authorize a live run. Confirm a usable environment-scoped key,
provider access and an approved all-in spending bound before any live invocation.
The controller requests a US$1 session limit; this is not a total billing cap.
A successful paid task produces a review patch and evidence, NOT a tested or
published app change. Generated code must undergo independent inspection and
credential-free isolated testing before a separate draft PR is considered.
There is no scheduler, automatic retry, merge or application deployment.
