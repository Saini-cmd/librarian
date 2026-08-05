# tests/

## Purpose
Sequential smoke-test / integration-test scripts for each pipeline stage. Run manually as standalone Python scripts (not pytest).

## Ownership
- `test_01_ingestion.py` — Clone + scan repos
- `test_02_chunking.py` — Chunk files into CodeChunks
- `test_03_embedding.py` — Full pipeline: ingest → chunk → embed
- `test_04_view_embedding.py` — Inspect stored embeddings in Qdrant
- `test_05_retrieval.py` — Hybrid retrieval with scoring
- `test_06_wipe_qdrant_db.py` — Delete & recreate Qdrant DB
- `test_07_answer_generation.py` — End-to-end retrieval + answer generation
- `test_08_summarization.py` — Per-file LLM summarization pipeline
- `bootstrap.py` — Path setup utility

## Local Contracts
- Tests run in numeric order for a full pipeline test
- No test runner; invoked as `python tests/test_XX_*.py`
- All tests import `bootstrap.ensure_repo_root()` for path setup

## Work Guidance
- New tests should follow the `test_XX_description.py` numbering scheme
- Use `bootstrap.py` for path setup; add assertions for regression testing

## Verification
- Run each test script individually: `python tests/test_XX_*.py`

## Child DOX Index
*None*
