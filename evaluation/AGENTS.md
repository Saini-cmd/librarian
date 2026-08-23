# evaluation/

## Purpose
Reproducible, URL-driven evaluation harness for the RAG pipeline. Given a repo URL, it ingests the repo twice (naive token chunks + AST chunks) into isolated Qdrant collections, builds a synthetic golden set from AST entities, runs four pipeline setups (S1 vector-on-naive, S2 vector-on-AST, S3 hybrid RRF, S4 hybrid + rerank), scores six metrics (Context Recall, Context Precision, MRR, Recall@K, Faithfulness, Answer Relevance), and emits a professional academic-style HTML report plus JSON/Markdown.

## Ownership
- `golden_set.py` — Golden-set construction: sample AST entities, DeepSeek-paraphrase into developer questions (symbol name hidden; prompt in `core/prompts.py`), retry+drop queries that leak the symbol name, cache/load committed JSON
- `ingest.py` — Ingest a repo twice (naive + AST) into `code_chunks_eval_naive` / `code_chunks_eval_ast`; incremental embedding, always cleans up the clone (unique per-run dir via `ingest()` → `(files, repo_dir)`, removed in `finally`); accepts an optional `progress(collection, done, total)` callback (per embed batch) for the CLI progress bar
- `pipelines.py` — S1–S4 setup runners composing existing retriever components; all setups return `final_top_k` ranked results for a fair comparison; S4 mirrors the production rerank-fallback (degraded results tagged `reranked: False`)
- `metrics.py` — The metrics: Context Recall/Precision, MRR, Recall@K (deterministic span math, **strict** line overlap per D15) + Faithfulness, Answer Relevance (DeepSeek-judged)
- `llm_judge.py` — DeepSeek judge wrappers for Faithfulness and Answer Relevance (coverage protocol, D16; prompts in `core/prompts.py`); `Judge.sanity_check()` verifies the judge discriminates good vs hallucinated answers; a failed call yields `None` (never fails a run)
- `charts.py` — Static matplotlib figures (PNG): grouped retrieval bars, component deltas, Recall@K curve, aggregate multi-repo chart
- `report.py` — Report data model (`EvalReport`) + JSON / Markdown / self-contained HTML renderers (`write_report`); PDF export via WeasyPrint (`report.pdf` / `aggregate.pdf`), gracefully skipped if WeasyPrint/system libs are missing
- `templates/report.css` — Academic journal styling for the HTML report
- `cli.py` — CLI entry: `python -m evaluation.cli --repo <url>` (repeatable), `--k`, `--n`, `--seed`, `--out`, `--regenerate-golden`, `--no-embed`, `--skip-generation`, `--config`; orchestrates ingest → golden set → S1–S4 → metrics → report; prints **stage banners (`1/4`–`4/4`) + tqdm progress bars** for embed batches, retrieval queries, and generation items; multi-repo aggregate report
- `runner.py` — Alias entry (`python -m evaluation.runner`) for `cli.py`
- `datasets/` — Committed per-repo golden-set JSON files (durable)

## Local Contracts
- **Metrics**: ground truth is span-based (`(file, line range)`); a retrieved chunk is relevant iff its span **strictly** overlaps the golden span in the same file (boundary-touching chunks are NOT relevant — D15). Works across both chunking strategies.
- Retrieval tables report mean ± per-question stdev; generation adds "Target in context" (fraction of questions whose ground-truth code reached the LLM context) — D18
- **Metric definitions**:
  - Context Recall = `|retrieved ∩ relevant| / |relevant in collection|`
  - Context Precision = `|retrieved ∩ relevant| / |retrieved|` — structurally capped at `1/K` (one target entity, K chunks returned); report states the ceiling — D33
  - MRR = mean reciprocal rank of the first relevant chunk (rank-1 hit = 1.0, rank-2 = 0.5, absent = 0) — the rank-quality metric (D33)
  - Recall@K = 1 if a relevant chunk is in the top-K else 0 (binary hit, averaged)
  - Faithfulness / Answer Relevance = DeepSeek judge scores (0–1)
- Generation metrics (Faithfulness, Answer Relevance) are computed on S4 only; "Target in context" (fraction of questions whose ground-truth code reached the LLM context) is a report diagnostic
- Citation evaluation was removed from the harness (D5 superseded) — chat citations remain an app feature but are not scored
- S4 mirrors the production pipeline exactly, including the rerank fallback: if reranking fails, results fall back to post-processed hybrid candidates with `"reranked": False` (see `DECISIONS.md` D13)
- Context curation knobs (`max_per_file`, `min_score`, `min_score_ratio`) default off; tune with `evaluation/context_ablation.py` (see `DECISIONS.md` D14)
- Eval uses dedicated collections `code_chunks_eval_naive` + `code_chunks_eval_ast`, scoped per repo via `repo_hash`; production `code_chunks` is never touched
- Golden sets are cached per repo in `datasets/<repo>_golden.json`; regenerate with an explicit flag
- Ingestion is incremental at the commit level: a commit already present in a collection is skipped (chunk ids are UUIDs, so per-chunk checks would never hit)
- Reports land in `data/eval_reports/<repo>_<ts>/` (runtime artifacts, not tracked)
- PDF export is optional: `report.pdf` / `aggregate.pdf` are rendered from the HTML via WeasyPrint when available; a missing WeasyPrint (or its system libs) logs a warning and skips PDF — never fails a run (D35)

## Work Guidance
- Every significant design decision must be recorded in `DECISIONS.md` (root)
- The harness composes existing production components (`VectorRetriever`, `BM25Index`, `HybridRetriever`, `OpenRouterReranker`, `AnswerGenerator`, `LLMClient`); do not fork production code
- A full run spends real API money (embeddings, rerank, judge/paraphrase calls); tests in `tests/` must be no-API where possible

## Verification
- `python tests/test_11_evaluation.py` — no-API unit smoke of metric math + golden-set selection + judge prompt assembly
- Manual live run: infra up, then `python -m evaluation.runner --repo <url>` (spends API)

## Child DOX Index
*None*
