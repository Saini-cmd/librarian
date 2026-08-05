# ingestion/

## Purpose
Clones a GitHub repository via `git clone --depth 1` and scans the local file tree, classifying files as AST-parsable, text-parsable, or unknown for downstream chunking. Cleanup (deleting the cloned repo) is the orchestrator's responsibility.

## Ownership
- `github_api_fetcher.py` — Shallow clone via `git clone --depth 1`, optionally authenticated with `GITHUB_TOKEN`
- `file_scanner.py` — Walk repo directory, classify files, enforce size limits
- `constants.py` — Extension maps and ignore patterns
- `ingestion_pipeline.py` — Orchestrates fetch → scan; stamps `repo` on each file's metadata

## Local Contracts
- Fetched repos stored in `data/repos/{repo_name}/`
- Shallow clone (`--depth 1`) — no git history
- File filtering (by extension, size, ignored dirs) happens in `FileScanner`, not during clone
- Requires `GITHUB_TOKEN` in `.env` for private repos (optional for public)
- Cleanup (deleting cloned repo) must be done by the orchestrator after embedding succeeds

## Work Guidance
- Adding a new AST language requires updating `constants.py` extension maps AND `chunking/ast_config.py` + `chunking/parser_manager.py`

## Verification
- Run `python tests/test_01_ingestion.py`

## Child DOX Index
*None*
