import logging

logger = logging.getLogger(__name__)

DEFAULT_INTENT_TERMS = [
    "implementation",
    "code example",
    "architecture",
    "flow",
    "design pattern",
    "handler",
    "middleware",
    "error handling",
    "configuration",
]


class QueryExpander:
    """Industry-grade query expansion for code RAG."""

    def __init__(self, intent_terms: list[str] | None = None):
        self.intent_terms = intent_terms or DEFAULT_INTENT_TERMS

    def expand(self, query: str) -> str:
        expanded_query = f"{query} {' '.join(self.intent_terms)}".strip()

        logger.info(
            "stage=query_expansion original=%s expanded_len=%d",
            query,
            len(expanded_query),
        )

        return expanded_query

    def expand_many(self, query: str) -> list[str]:
        expanded_queries = [query]

        for term in self.intent_terms:
            expanded_queries.append(f"{query} {term}")

        logger.info(
            "stage=query_expansion_many original=%s expanded_count=%d",
            query,
            len(expanded_queries),
        )

        return expanded_queries