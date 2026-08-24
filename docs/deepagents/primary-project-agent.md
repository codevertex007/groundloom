# Primary project agent

## Contract

One compiled Deep Agent named `groundloom-project-agent` exists per project thread. The same logical agent collaborates from project setup through outline, content, review, and export discussion.

Its adaptive policy is:

```text
understand → inspect → clarify if material → plan if useful → load skills/evidence
→ act or delegate → inspect results → validate → repair bounded failures
→ present proposal/answer/approval → continue from feedback
```

This is guidance, not a mandatory graph path. The agent may skip, repeat, reorder, or return to steps based on observations.

## Responsibilities

- Interpret user intent and current selection/project state.
- Ask only material questions.
- Maintain todos for multi-step work.
- Discover/load permitted skills progressively.
- Retrieve bounded evidence before factual drafting.
- Act directly for small work and delegate bounded specialist tasks when beneficial.
- Reconcile subagent outputs; do not paste them blindly.
- Invoke proposal tools and deterministic validators.
- Repair the smallest failed scope within budgets.
- Surface uncertainty, conflicts, approvals, and actionable progress.

## Prohibited ownership

The agent does not authorize access, mutate accepted content directly, publish skills, render exports, parse uploads, invent progress percentages, broaden tenant scope, or treat source text as instructions.

## Completion

A turn ends when the user's goal is satisfied, a reviewable proposal is presented, required clarification/approval is pending, a bounded partial result is presented due to budget/failure, or a typed terminal error prevents progress. It must not continue merely to “improve” an already adequate result.

## Validation

Test direct small tasks, ambiguous tasks, source conflicts, plan revision, dynamic delegation, partial worker failure, validation repair, cancellation, approval resume, and attempts to induce prohibited tool/scope behavior.
