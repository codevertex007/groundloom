# ADR-001: One persistent primary Deep Agent per project

**Status:** Accepted

## Context
The product spans setup, research, generation, editing, and review. Fixed phase agents lose continuity and make routing a bottleneck.

## Decision
Use one persistent primary project agent/thread to own the adaptive semantic loop, with bounded specialist subagents and deterministic services around it.

## Consequences
Prompt/context discipline and trajectory evaluation become critical. Semantic sequence stays flexible; infrastructure invariants remain outside model control.

## Validation
Tests prove same-thread continuity, stage skipping/revisiting, direct work, dynamic delegation, and mandatory hook enforcement.
