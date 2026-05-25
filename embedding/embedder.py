from sentence_transformers import SentenceTransformer
from typing import List
from chunking.chunk_model import CodeChunk
import torch

class Embedder:
    def __init__(self, model_name: str = "BAAI/bge-large-en-v1.5"):

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[Embedder] Using device: {self.device}")

        self.batch_size = 64 if self.device == "cuda" else 16  #=============================================================== 64 or 16s

        self.model = SentenceTransformer(
            model_name,
            device=self.device
        )

        self.embedding_dim = self.model.get_sentence_embedding_dimension()
        print(f"[Embedder] Embedding dimension: {self.embedding_dim}")

    def embed_texts(self, texts: List[str]):
        return self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=True,
            batch_size=self.batch_size
        )

    def embed_chunks(self, chunks: List[CodeChunk]):
        texts = [self._prepare_text(chunk) for chunk in chunks]
        embeddings = self.embed_texts(texts)
        return embeddings

    def _prepare_text(self, chunk: CodeChunk):

        # Structured metadata improves retrieval quality
        return (
            f"Repository: {chunk.repo}\n"
            f"File: {chunk.file_path}\n"
            f"Language: {chunk.language}\n"
            f"Symbol: {chunk.symbol}\n"
            f"Node Type: {chunk.node_type}\n"
            f"Chunk Source: {chunk.chunk_source}\n"
            f"Lines: {chunk.start_line}-{chunk.end_line}\n\n"
            f"{chunk.content}"
        )