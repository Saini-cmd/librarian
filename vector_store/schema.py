from qdrant_client.models import VectorParams, Distance

def get_vector_params(embedding_dim: int):
    return VectorParams(
        size=embedding_dim,
        distance=Distance.COSINE
    )