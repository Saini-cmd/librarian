import logging
from typing import Sequence

from sentence_transformers import SentenceTransformer


logger = logging.getLogger(__name__)


class QueryEmbedder:
    """Encodes user queries into dense vectors for vector search."""

    def __init__(self, model_name: str = "BAAI/bge-large-en-v1.5", device: str | None = None):
        self.model = SentenceTransformer(model_name, device=device)
        self.model_name = model_name
        logger.info("Initialized QueryEmbedder with model=%s", model_name)

    def embed_query(self, query: str) -> list[float]:
        embedding = self.model.encode(
            [query],
            normalize_embeddings=True,
            show_progress_bar=False,
        )[0]
        return embedding.tolist()

    def embed_queries(self, queries: Sequence[str]) -> list[list[float]]:
        embeddings = self.model.encode(
            list(queries),
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in embeddings]
