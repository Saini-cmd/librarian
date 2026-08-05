from qdrant_client.models import (
    VectorParams,
    Distance,
    SparseVectorParams,
    SparseIndexParams,
    Modifier,
)


VECTOR_NAME = "text_dense"
VECTOR_SIZE = 768
SPARSE_VECTOR_NAME = "text_sparse"


def get_vector_params(embedding_dim: int = VECTOR_SIZE):
    return {
        VECTOR_NAME: VectorParams(
            size=embedding_dim,
            distance=Distance.COSINE,
        )
    }


def get_sparse_vector_params():
    return {
        SPARSE_VECTOR_NAME: SparseVectorParams(
            index=SparseIndexParams(on_disk=True),
            modifier=Modifier.IDF,
        )
    }
