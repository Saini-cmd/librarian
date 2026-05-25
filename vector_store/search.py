from qdrant_client.models import Filter
from embedding.embedder import Embedder
from .qdrant_client import QdrantManager

class VectorSearcher:
    def __init__(self, collection_name: str):
        self.collection_name = collection_name
        self.qdrant = QdrantManager().get_client()
        self.embedder = Embedder()

    def search(self, query: str, top_k: int = 10):
        print(f"[VectorSearcher] Query: {query}")

        query_embedding = self.embedder.embed_texts([query])[0]

        results = self.qdrant.query_points(
            collection_name=self.collection_name,
            query=query_embedding.tolist(),
            limit=top_k
        )

        return results.points