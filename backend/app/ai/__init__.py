"""Groundloom AI harness package.

The package is intentionally organized by Deep Agents concern: runtime,
middleware, scoped tools, subagents, providers, prompts, and execution state.
Provider SDKs are imported lazily by the runtime so local mode stays credential
free and importable.
"""
