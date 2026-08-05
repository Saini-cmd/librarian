from bootstrap import ensure_repo_root

ensure_repo_root()

from ingestion.ingestion_pipeline import IngestionPipeline
from chunking.chunk_pipeline import ChunkPipeline
from embedding.embedding_pipeline import EmbeddingPipeline


REPOS = [
    "https://github.com/Saini-cmd/lynko.git",
]


def main():
    ingestion = IngestionPipeline()
    chunker = ChunkPipeline()
    embedder = EmbeddingPipeline()

    for repo_url in REPOS:
        print(f"\nProcessing: {repo_url}")

        files = ingestion.ingest(repo_url)
        chunks = chunker.chunk_repository(files)
        print(f"Total chunks: {len(chunks)}")

        embedder.embed_chunks(chunks)


if __name__ == "__main__":
    main()
