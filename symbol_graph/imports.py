"""Per-language import extraction + best-effort resolution to repo files.

Consumed by `symbol_graph.graph_builder` to emit `imports` (file -> file) edges.
All resolution is best-effort: refs that cannot be matched to a repo file
(external packages, stdlib, unknown layout) resolve to `None` and are dropped.

Conventions:
- `extract_import_refs(language, content)` returns the raw references found in
  a chunk's code (import statements, `use`/`using`/`require`/`#include`...).
- `resolve_import(ref, source_file, repo_files, language, ts_aliases=None)`
  maps one reference to a repo-relative file path, or `None`.
- `load_ts_aliases(chunks)` parses a `tsconfig.json`/`jsconfig.json` text chunk
  into a `{alias: repo-relative-target}` map (baseUrl-relative) used to expand
  `@/...`-style import specifiers.
"""

import json
import os
import re


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

_IMPORT_PATTERNS: dict[str, list[re.Pattern]] = {
    "javascript": [
        re.compile(r"(?:import|export)\s+[^'\"`]*?\s+from\s+['\"]([^'\"]+)['\"]"),
        re.compile(r"(?:import|require)\(\s*['\"]([^'\"]+)['\"]\s*\)"),
        re.compile(r"import\s+['\"]([^'\"]+)['\"]"),
    ],
    "typescript": [
        re.compile(r"(?:import|export)\s+[^'\"`]*?\s+from\s+['\"]([^'\"]+)['\"]"),
        re.compile(r"(?:import|require)\(\s*['\"]([^'\"]+)['\"]\s*\)"),
        re.compile(r"import\s+['\"]([^'\"]+)['\"]"),
        re.compile(r"import\s+[\w]+\s*=\s*require\(\s*['\"]([^'\"]+)['\"]\s*\)"),
    ],
    "tsx": [
        re.compile(r"(?:import|export)\s+[^'\"`]*?\s+from\s+['\"]([^'\"]+)['\"]"),
        re.compile(r"(?:import|require)\(\s*['\"]([^'\"]+)['\"]\s*\)"),
        re.compile(r"import\s+['\"]([^'\"]+)['\"]"),
        re.compile(r"import\s+[\w]+\s*=\s*require\(\s*['\"]([^'\"]+)['\"]\s*\)"),
    ],
    "python": [
        re.compile(r"^\s*import\s+([\w.]+)", re.M),
        re.compile(r"^\s*from\s+([\w.]+)\s+import", re.M),
    ],
    "java": [
        re.compile(r"^\s*import\s+(?:static\s+)?([\w*]+(?:\.[\w*]+)*)\s*;", re.M),
    ],
    "kotlin": [
        re.compile(r"^\s*import\s+([\w*]+(?:\.[\w*]+)*)", re.M),
    ],
    "c": [
        re.compile(r'#include\s*"([^"]+)"'),
        re.compile(r"#include\s*<([^>]+)>"),
    ],
    "cpp": [
        re.compile(r'#include\s*"([^"]+)"'),
        re.compile(r"#include\s*<([^>]+)>"),
    ],
    "rust": [
        re.compile(r"^\s*use\s+([\w:]+)", re.M),
        re.compile(r"^\s*(?:pub(?:\(crate\))?\s+)?mod\s+([\w]+)\s*;", re.M),
    ],
    "csharp": [
        re.compile(r"^\s*using\s+[\w.]+\s*=\s*([\w.]+)\s*;", re.M),
        re.compile(r"^\s*using\s+(?:static\s+)?([\w.]+)\s*;", re.M),
    ],
    "ruby": [
        re.compile(r"^\s*require(?:_relative)?\s+['\"]([^'\"]+)['\"]", re.M),
    ],
    "go": [
        # single-line `import "pkg"` and `import (\n "a" \n "b" \n)` blocks
        re.compile(r"import\s+(?:\(\s*([^)]*?)\s*\)|([\"'][^\"']+[\"']))", re.S),
    ],
}


def extract_import_refs(language: str, content: str) -> list[str]:
    refs: list[str] = []
    for pattern in _IMPORT_PATTERNS.get(language, []):
        for match in pattern.finditer(content):
            if language == "go":
                if match.group(1) is not None:
                    refs.extend(re.findall(r"[\"']([^\"']+)[\"']", match.group(1)))
                else:
                    ref = (match.group(2) or "").strip().strip("\"'")
                    if ref:
                        refs.append(ref)
            else:
                ref = match.group(1).strip()
                if ref:
                    refs.append(ref)
    return refs


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------


def _first_match(repo_files: set[str], candidates: list[str]) -> str | None:
    """First candidate found among repo files (exact or suffix/dir match)."""
    for cand in candidates:
        if not cand:
            continue
        if cand in repo_files:
            return cand
        if cand.endswith("/"):
            prefix = cand.rstrip("/")
            for rf in sorted(repo_files):
                if os.path.dirname(rf).endswith(prefix):
                    return rf
            continue
        for rf in repo_files:
            if rf.endswith(cand):
                return rf
    return None


_JS_TS_SUFFIXES = (
    "", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    "/index.js", "/index.jsx", "/index.ts", "/index.tsx",
)


def _resolve_ts_path(path: str, repo_files: set[str]) -> str | None:
    """Resolve a (base-joined or repo-root-relative) TS/JS path with suffixes."""
    return _first_match(repo_files, [os.path.normpath(path + s) for s in _JS_TS_SUFFIXES])


def _python_package_bases(source_file: str, repo_files: set[str]) -> list[str]:
    """Package-root chain (ancestors with __init__.py) + repo root, innermost first."""
    bases: list[str] = []
    d = os.path.dirname(source_file)
    seen: set[str] = set()
    while d and d not in seen:
        seen.add(d)
        if os.path.join(d, "__init__.py") in repo_files:
            bases.append(d)
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    bases.append("")
    return bases


def _expand_ts_alias(ref: str, aliases: dict[str, str]) -> str | None:
    """Expand a tsconfig `paths` alias (with `*` wildcard) to a repo-root path."""
    best: tuple[int, str] | None = None
    for key, target in aliases.items():
        if "*" in key:
            prefix, suffix = key.split("*", 1)
            if ref.startswith(prefix) and ref.endswith(suffix) and len(ref) > len(prefix) + len(suffix):
                wild = ref[len(prefix): len(ref) - len(suffix)]
                cand = target.replace("*", wild)
                if best is None or len(key) > best[0]:
                    best = (len(key), cand)
        else:
            if ref == key or ref.startswith(key + "/"):
                cand = target + ref[len(key):]
                if best is None or len(key) > best[0]:
                    best = (len(key), cand)
    return best[1] if best else None


# ---------------------------------------------------------------------------
# Per-language resolution
# ---------------------------------------------------------------------------


def _resolve_js_ts(ref: str, source_file: str, repo_files: set[str], ts_aliases: dict | None) -> str | None:
    if ts_aliases and not ref.startswith("."):
        expanded = _expand_ts_alias(ref, ts_aliases)
        if expanded:
            return _resolve_ts_path(expanded, repo_files)
    if not ref.startswith("."):
        return None  # bare specifier (external package)
    base = os.path.dirname(source_file)
    return _resolve_ts_path(os.path.join(base, ref), repo_files)


def _resolve_python(ref: str, source_file: str, repo_files: set[str]) -> str | None:
    base = os.path.dirname(source_file)
    if ref.startswith("."):
        dots = len(ref) - len(ref.lstrip("."))
        parts = [p for p in ref.split(".") if p]
        pkg = base
        for _ in range(dots - 1):
            pkg = os.path.dirname(pkg)
        if parts:
            mod = "/".join(parts)
            return _first_match(repo_files, [os.path.join(pkg, mod + ".py"), os.path.join(pkg, mod, "__init__.py")])
        return _first_match(repo_files, [os.path.join(pkg, "__init__.py")])
    normalized = ref.replace(".", "/")
    for b in _python_package_bases(source_file, repo_files):
        hit = _first_match(repo_files, [f"{b}/{normalized}.py".lstrip("/"), f"{b}/{normalized}/__init__.py".lstrip("/")])
        if hit:
            return hit
    return None


_JVM_SRC_ROOTS = ("src/main/java/", "src/main/kotlin/", "src/", "")


def _resolve_jvm(ref: str, repo_files: set[str], language: str) -> str | None:
    ext = ".java" if language == "java" else ".kt"
    ref = ref.rstrip("*").rstrip(".")
    segments = [s for s in ref.replace(".", "/").split("/") if s]
    for i in range(len(segments), 0, -1):
        sub = "/".join(segments[:i])
        candidates = []
        for root in _JVM_SRC_ROOTS:
            candidates.append(f"{root}{sub}{ext}")
            candidates.append(f"{root}{sub}/")
        hit = _first_match(repo_files, candidates)
        if hit:
            return hit
    return None


def _resolve_c_cpp(ref: str, source_file: str, repo_files: set[str]) -> str | None:
    base = os.path.dirname(source_file)
    candidates: list[str] = []
    d = base
    seen: set[str] = set()
    while d and d not in seen:  # source dir + each ancestor dir (include dirs)
        seen.add(d)
        candidates.append(os.path.normpath(os.path.join(d, ref)))
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    candidates.append(os.path.normpath(ref))  # repo-root relative (angle includes)
    candidates.append(os.path.normpath(os.path.join("src", ref)))  # src-root relative
    return _first_match(repo_files, candidates)


def _resolve_rust(ref: str, source_file: str, repo_files: set[str]) -> str | None:
    segs = [s for s in ref.split("::") if s]
    if not segs:
        return None
    head = segs[0]
    if head == "crate":
        base, rest = "src", segs[1:]
    elif head == "super":
        base, rest = os.path.dirname(os.path.dirname(source_file)), segs[1:]
    elif head == "self":
        base, rest = os.path.dirname(source_file), segs[1:]
    elif head in ("std", "core", "alloc", "proc_macro"):
        return None  # std/core crates
    else:
        base, rest = "src", segs
    if not rest:
        return None
    module = "/".join(rest[:-1] if len(rest) > 1 else rest)
    if base:
        return _first_match(repo_files, [f"{base}/{module}.rs", f"{base}/{module}/mod.rs"])
    return _first_match(repo_files, [f"{module}.rs", f"{module}/mod.rs"])


def _resolve_csharp(ref: str, repo_files: set[str]) -> str | None:
    ref = ref.rstrip("*").rstrip(".")
    segments = [s for s in ref.replace(".", "/").split("/") if s]
    for i in range(len(segments), 0, -1):
        sub = "/".join(segments[:i])
        hit = _first_match(repo_files, [f"{sub}.cs", f"{sub}/"])
        if hit:
            return hit
    return None


def _resolve_go(ref: str, repo_files: set[str]) -> str | None:
    go_dirs: dict[str, list[str]] = {}
    for rf in repo_files:
        if rf.endswith(".go"):
            go_dirs.setdefault(os.path.dirname(rf), []).append(rf)
    if not go_dirs:
        return None
    path = ref.strip("/")
    best: tuple[int, str] | None = None
    for d, files in go_dirs.items():
        files.sort()
        if d == path or d.endswith("/" + path):
            if best is None or len(d) > best[0]:
                best = (len(d), files[0])
    return best[1] if best else None


def _resolve_ruby(ref: str, source_file: str, repo_files: set[str]) -> str | None:
    base = os.path.dirname(source_file)
    if ref.startswith("."):
        candidates = [os.path.normpath(os.path.join(base, ref + ".rb"))]
    else:
        normalized = ref.replace(".", "/")
        candidates = [f"{normalized}.rb", f"lib/{normalized}.rb"]
    return _first_match(repo_files, candidates)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_import(
    ref: str,
    source_file: str,
    repo_files: set[str],
    language: str,
    ts_aliases: dict | None = None,
) -> str | None:
    """Best-effort resolution of an import/module reference to a repo file."""
    if not ref:
        return None

    if language in ("javascript", "typescript", "tsx"):
        return _resolve_js_ts(ref, source_file, repo_files, ts_aliases)
    if language == "python":
        return _resolve_python(ref, source_file, repo_files)
    if language in ("java", "kotlin"):
        return _resolve_jvm(ref, repo_files, language)
    if language in ("c", "cpp"):
        return _resolve_c_cpp(ref, source_file, repo_files)
    if language == "rust":
        return _resolve_rust(ref, source_file, repo_files)
    if language == "csharp":
        return _resolve_csharp(ref, repo_files)
    if language == "go":
        return _resolve_go(ref, repo_files)
    if language == "ruby":
        return _resolve_ruby(ref, source_file, repo_files)
    return None


def load_ts_aliases(chunks) -> dict[str, str]:
    """Build a tsconfig/jsconfig `paths` alias map from the repo's config chunk."""
    for c in chunks:
        if c.file_path in ("tsconfig.json", "jsconfig.json"):
            try:
                data = json.loads(c.content)
                opts = data.get("compilerOptions", {}) or {}
                base_url = opts.get("baseUrl") or "."
                aliases: dict[str, str] = {}
                for key, targets in (opts.get("paths") or {}).items():
                    if targets:
                        aliases[key] = os.path.normpath(os.path.join(base_url, targets[0]))
                return aliases
            except Exception:
                return {}
    return {}
