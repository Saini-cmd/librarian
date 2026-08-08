# ingestion/

## Purpose
Clones a GitHub repository via `git clone --depth 1` and scans the local file tree, classifying files as AST-parsable, text-parsable, or unknown for downstream chunking. Also provides the cheap remote change probe (`git ls-remote`) used by `/api/process` and sync. Cleanup (deleting the cloned repo) is the orchestrator's responsibility.

## Ownership
- `github_api_fetcher.py` — Shallow clone via `git clone --depth 1` (optional `force=True` re-clone), `remote_head_sha()` change probe, optionally authenticated with `GITHUB_TOKEN`
- `file_scanner.py` — Walk repo directory, classify files, enforce size limits
- `constants.py` — Extension maps and ignore patterns
- `ingestion_pipeline.py` — Orchestrates fetch → scan; stamps `repo_url` on each file's metadata

## Local Contracts
- Fetched repos stored in `data/repos/{repo_name}/`; `fetch_repo(force=True)` removes an existing dir before re-cloning (used by sync)
- Shallow clone (`--depth 1`) — no git history
- `GitHubAPIFetcher.head_sha(repo_path)` returns the current HEAD commit SHA (works on shallow clones) — used by the orchestrator as the per-commit identity (`repo_hash`)
- `GitHubAPIFetcher.remote_head_sha(repo_url)` returns the remote HEAD SHA without cloning (`git ls-remote <auth_url> HEAD`) — the change probe; raises on failure (private repo / missing token)
- Expects a **canonical https URL** (normalized upstream by `orchestrator.run` via `backend.state.normalize_repo_url`) — scp-style/ssh forms are never passed in; no URL-form knowledge lives here
- File filtering (by extension, size, ignored dirs) happens in `FileScanner`, not during clone
- Requires `GITHUB_TOKEN` in `.env` for private repos (optional for public)
- Cleanup (deleting cloned repo) must be done by the orchestrator after embedding succeeds

## Work Guidance
- Adding a new AST language requires updating `constants.py` extension maps AND `chunking/ast_config.py` + `chunking/parser_manager.py`

## Verification
- Run `python tests/test_01_ingestion.py`

## Child DOX Index
*None*
