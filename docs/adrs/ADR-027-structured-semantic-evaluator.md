# ADR-027: structured semantic evaluator adapter

**Status:** Accepted  
**Date:** 2026-08-25

## Decision

Keep the deterministic rubric grader as the mandatory local and invariant
baseline, and add an optional OpenAI-compatible structured semantic evaluator
behind the existing `Grader` protocol. As amended by ADR-035, the adapter uses
LangChain `ChatPromptTemplate`, `ChatOpenAI`, and model-level Pydantic
structured output. It sends bounded draft text, bounded citation IDs, and
rubric metadata and accepts only a validated score, verdict, and bounded
feedback strings.

Semantic feedback is observational/review input. It cannot authorize a
canonical mutation, replace deterministic citation/structure checks, broaden
source scope, or silently fall back to another provider. Provider errors and
malformed results are typed, retry-aware where appropriate, and redacted.

## Consequences

The same evaluation cases can run locally or against a pinned provider profile,
which makes quality-control comparisons explicit. Production still needs
provider credentials, rubric baselines, evaluator quality review, and
Langfuse/feedback promotion evidence; the local adapter remains fully runnable
without them.
