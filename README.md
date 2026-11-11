# Skycar bot runner

An isolated home for Skycar's bot setup. This repository contains no application, customer data, credentials, or hosting configuration.

## Current capability

The **Skycar bot safety preflight** workflow is manual-only and requires owner approval through the `skycar-agent-pilot` environment. It uses a read-only GitHub token, checks out an immutable public Skycar source revision, verifies the offline request fingerprint, and runs 29 credential-free safety and routing tests.

- Source: [Skycar pilot commit f10a36f](https://github.com/jimmoq-hopsup-Hoqde6/skycar-site/commit/f10a36fe98961dc1dcfbace37d9323752e1f3ffe)
- Controller review: [Skycar PR #95](https://github.com/jimmoq-hopsup-Hoqde6/skycar-site/pull/95)
- Original workflow review: [Skycar PR #96](https://github.com/jimmoq-hopsup-Hoqde6/skycar-site/pull/96)

There is no OpenAI API key, paid execution step, schedule, automatic code publishing, application deployment, or connection to a hosting project. The budget printed by the preflight describes a proposed future session, not a payment authorization.

## Before live coding

Live coding needs separate owner approval for the exact task, source files, credential scope and spending limit. It also needs verified billing, a securely configured restricted key, reviewed execution code, and post-run artifact testing. Completing this preflight does not mean an autonomous coding bot is active.

## Safety boundaries

The Skycar application repository and its branch protections remain separate and unchanged. Do not add paid execution or automatic publishing without the required owner approvals. Do not add production secrets or customer data to this repository.
