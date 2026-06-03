import logging
from rag.local.context_builder import ContextBuilder as LocalContextBuilder


logger = logging.getLogger(__name__)


class ContextBuilder(LocalContextBuilder):
    """External context builder.

    Currently reuses the local `ContextBuilder` implementation but exists so
    external-specific heuristics (larger token budgets, different dedupe)
    can be introduced independently.
    """

    def __init__(self, max_chunks: int = 12, token_budget: int = 20000):
        super().__init__(max_chunks=max_chunks, token_budget=token_budget)
