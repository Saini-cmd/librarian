# Librarian AI

Code RAG for repository ingestion, semantic chunking, embedding, hybrid retrieval, reranking, and local answer generation.

## What It Does

- Clones source repositories into `data/repos/`
- Scans and classifies files for AST-based or text-based chunking
- Produces `CodeChunk` records for embedding and retrieval
- Stores vectors in local Qdrant under `qdrant_db/`
- Retrieves context with vector search, BM25, RRF, and reranking
- Generates answers from retrieved code context with a local Ollama model

## Local LLM

Answer generation uses Ollama, not a hosted API.

- Model: `gemma4:e2b-it-q4_K_M`
- Base URL: `http://localhost:11434`

Make sure `ollama serve` is running and the model is installed before testing.

## Quick Start

1. Activate the project environment.

   ```bash
   source venv/bin/activate
   ```

2. Verify Ollama sees the model.

   ```bash
   ollama list
   ```

3. Run the answer-generation smoke test.

   ```bash
   python tests/test_07_answer_generation.py
   ```

## Useful Scripts

- `python tests/test_01_ingestion.py` - clone and scan repositories
- `python tests/test_02_chunking.py` - chunk files into `CodeChunk` objects
- `python tests/test_03_embedding.py` - embed chunks and store them in Qdrant
- `python tests/test_04_view_embedding.py` - inspect stored embeddings
- `python tests/test_05_retrieval.py` - run retrieval and print expanded queries
- `python tests/test_06_wipe_qdrant_db.py` - clear the local Qdrant database
- `python tests/test_07_answer_generation.py` - end-to-end retrieval + answer generation

## Generated Data

These paths are intentionally ignored by git because they are derived at runtime:

- `.env`
- `venv/`
- `data/chunks/`
- `data/repos/`
- `qdrant_db/`
- cache folders like `__pycache__/`

If you need a clean run, wipe the local database and regenerate the artifacts from the scripts above.

## Repository Layout

- `ingestion/` - repo cloning and file scanning
- `chunking/` - AST and text chunking
- `embedding/` - chunk embedding pipeline
- `retrieval/` - hybrid retrieval, RRF, and query expansion
- `reranking/` - cross-encoder reranking
- `rag/` - context building, prompt building, Ollama client, and answer generation
- `vector_store/` - local Qdrant client and schema helpers
