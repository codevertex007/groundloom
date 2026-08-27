"""Groundloom-specific AI capabilities and the Deep Agents composition root.

Reusable framework mechanics live in ``groundloom_harness``. This package owns
Groundloom prompts, retrieval, evaluation, tools, subagents, and composition;
backend persistence is accessed only through typed application ports (see
``ports.py``). It intentionally has no SQLAlchemy or tenant-context imports.

The authorized adapter that implements those ports with a real database
session and workspace/project scope lives in ``app.integrations.ai`` — a
separate package by design, not a duplicate. See
``docs/architecture/ai-contribution-boundary.md`` for the ownership split.
"""
