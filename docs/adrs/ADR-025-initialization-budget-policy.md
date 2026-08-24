# ADR-025: Exclude Primary-Thread Initialization from Optional-Work Budgets

## Status

Accepted — 2026-08-25

## Context

Project creation starts the persistent primary-agent thread after the project
transaction commits. The initialization turn establishes the thread and its
durable readiness state; it does not perform optional drafting, retrieval, or
canonical content work. Applying a deliberately small user work budget to that
setup turn could leave a new project waiting before its first user request and
would make the project appear unusable.

## Decision

The deterministic local initialization turn is exempt from per-run and
workspace optional-work budget enforcement. It still creates a normal durable
run, emits the normal lifecycle events, is serialized with other project turns,
and is subject to authorization, cancellation, leasing, retry, and audit rules.
All non-initialization user turns remain subject to the configured per-run and
workspace token, tool-call, and cost budgets.

## Consequences

- A newly created project can accept its first user turn even when its configured
  optional-work budget is intentionally small.
- Initialization is still visible and recoverable as a durable run.
- The local runtime has a narrow special case; production Deep Agents provider
  initialization remains subject to the provider adapter's own startup and
  operational policies.
- Budget tests must distinguish thread setup from optional semantic work.

## Alternatives rejected

- Removing the initialization run would violate the persistent-thread lifecycle
  contract.
- Raising the user budget implicitly would hide the configured policy and make
  budget behavior non-reproducible.
- Allowing concurrent first-turn work would violate the one-active-turn
  invariant.
