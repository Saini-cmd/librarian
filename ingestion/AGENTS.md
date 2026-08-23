# ingestion/

## Purpose
Clones a GitHub repository via `git clone --depth 1` and scans the local file tree, classifying files as AST-parsable, text-parsable, or unknown for downstream chunking. Also provides the cheap remote change probe (`git ls-remote`) used by `/api/process` and sync. Cleanup (deleting the cloned repo) is the orchestrator's responsibility.

## Ownership
- `github_api_fetcher.py` — Shallow clone via `git clone --depth 1` into a **unique per-run dir**, `remote_head_sha()` change probe, optionally authenticated with `GITHUB_TOKEN`
- `file_scanner.py` — Walk repo directory, classify files, enforce size limits
- `constants.py` — Extension maps and ignore patterns
- `ingestion_pipeline.py` — Orchestrates fetch → scan; stamps `repo_url` on each file's metadata; `ingest()` returns `(files, repo_dir)` so the caller gets the clone path

## Local Contracts
- Fetched repos stored in `data/repos/{repo_name}-{12-hex uuid}/` — a **unique directory per clone call**, so concurrent ingests never share (or delete each other's) clone. Partial clones are removed on failure. The caller (orchestrator / eval / tests) must delete the returned dir after use
- `ingest(repo_url)` returns `(files, repo_dir)` — `repo_dir` is the exact unique clone path (for `head_sha` + cleanup); do not re-derive it from the repo name
- Shallow clone (`--depth 1`) — no git history
- `GitHubAPIFetcher.head_sha(repo_path)` returns the current HEAD commit SHA (works on shallow clones) — used by the orchestrator as the per-commit identity (`repo_hash`)
- `GitHubAPIFetcher.remote_head_sha(repo_url)` returns the remote HEAD SHA without cloning (`git ls-remote <auth_url> HEAD`) — the change probe; raises on failure (private repo / missing token)
- Expects a **canonical https URL** (normalized upstream by `orchestrator.run` via `core.url.normalize_repo_url`) — scp-style/ssh forms are never passed in; no URL-form knowledge lives here
- File filtering (by extension, size, ignored dirs) happens in `FileScanner`, not during clone
- Requires `GITHUB_TOKEN` in `.env` for private repos (optional for public)
- Cleanup (deleting the cloned repo) must be done by the caller after embedding succeeds

## Work Guidance
- Adding a new AST language requires updating `constants.py` extension maps AND `chunking/ast_config.py` + `chunking/parser_manager.py`

## Verification
- Run `python tests/test_01_ingestion.py`

## Child DOX Index
*None*
