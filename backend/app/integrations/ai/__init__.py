"""Backend-owned adapters consumed by Groundloom AI capabilities.

This is the authorized side of the AI boundary: it holds a real database
session and tenant/workspace ``RuntimeContext`` and implements the typed
ports declared in ``app.ai`` (e.g. ``AgentServicePort``, ``RetrievalRepository``).
``app.ai`` itself never imports SQLAlchemy or this package — see
``docs/architecture/ai-contribution-boundary.md`` for why the two packages
are split rather than merged.
"""

from .retrieval import search_evidence

__all__ = ["search_evidence"]
