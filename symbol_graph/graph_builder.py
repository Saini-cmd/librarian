import os
import re
from typing import Any

from qdrant_client.models import FieldCondition, Filter, MatchValue

from chunking.parser_manager import ParserManager
from vector_store.indexer import chunk_from_payload
from vector_store.qdrant_client import QdrantManager


COLLECTION_NAME = "code_chunks"
MAX_SNIPPET_CHARS = 4000
MIN_SYMBOL_LEN = 2

KIND_MAP = {
    "class_definition": "class",
    "class_declaration": "class",
    "class_specifier": "class",
    "interface_declaration": "interface",
    "object_declaration": "class",
    "struct_item": "class",
    "impl_item": "impl",
    "type_declaration": "class",
    "class": "class",
    "function_definition": "function",
    "function_declaration": "function",
    "function_item": "function",
    "def": "function",
    "method_definition": "method",
    "method_declaration": "method",
}


def _load_repo_chunks(repo_name: str) -> list[Any]:
    client = QdrantManager().get_client()
    chunks: list[Any] = []
    offset = None
    scroll_filter = Filter(
        must=[FieldCondition(key="repo", match=MatchValue(value=repo_name))]
    )
    while True:
        points, next_offset = client.scroll(
            collection_name=COLLECTION_NAME,
            limit=512,
            offset=offset,
            scroll_filter=scroll_filter,
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            break
        for point in points:
            chunk = chunk_from_payload(point.payload or {})
            if chunk is not None:
                chunks.append(chunk)
        if next_offset is None:
            break
        offset = next_offset
    return chunks


def _kind(node_type: str) -> str:
    return KIND_MAP.get(node_type, "entity")


_PARSER_MANAGER = ParserManager()
_PARSERS: dict[str, Any] = {}


def _get_parser(language: str):
    if not language:
        return None
    if language not in _PARSERS:
        try:
            _PARSERS[language] = _PARSER_MANAGER.get_parser(language)
        except Exception:
            _PARSERS[language] = None
    return _PARSERS.get(language)


def _parse(language: str, content: str):
    if not language or not content:
        return None
    parser = _get_parser(language)
    if parser is None:
        return None
    try:
        return parser.parse(content.encode("utf-8"))
    except Exception:
        return None


def _identifiers_for_content(language: str, content: str) -> set[str]:
    """Return identifier/type_identifier names found in a code snippet.

    Collects every node whose type ends with 'identifier' (identifier,
    type_identifier, field_identifier, property_identifier, method_identifier),
    which covers real references across tree-sitter grammars. Unsupported
    languages or parse errors are skipped gracefully.
    """
    tree = _parse(language, content)
    if tree is None:
        return set()
    idents: set[str] = set()
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type.endswith("identifier"):
            text = node.text
            if text:
                try:
                    idents.add(text.decode("utf-8"))
                except Exception:
                    pass
        stack.extend(node.children)
    return idents


_JS_TS_LANGS = {"javascript", "typescript", "tsx"}
_COMPONENT_VALUE_TYPES = {
    "arrow_function",
    "function_expression",
    "generator_function",
    "class_expression",
}
_COMPONENT_BOUNDARY_TYPES = _COMPONENT_VALUE_TYPES | {
    "function_declaration",
    "function_definition",
    "method_definition",
    "class_declaration",
    "class_definition",
    "object",
    "statement_block",
    "template_string",
}


def _js_component_declarations(language: str, content: str, start_line: int) -> list[dict[str, Any]]:
    """Find `const X = () => ...` / function-expression components in a snippet.

    React/JS components written as arrow or function expressions are
    `variable_declarator` nodes (not function/class declarations), so the AST
    chunker misses them. This scans JS/TS text chunks and returns module-level
    declarators whose value is a function/class expression, so the graph can
    include them as entities.
    """
    if language not in _JS_TS_LANGS:
        return []
    tree = _parse(language, content)
    if tree is None:
        return []
    results: list[dict[str, Any]] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == "variable_declarator":
            name_node = node.child_by_field_name("name")
            value_node = node.child_by_field_name("value")
            if (
                name_node is not None
                and name_node.type == "identifier"
                and value_node is not None
                and value_node.type in _COMPONENT_VALUE_TYPES
            ):
                try:
                    name = name_node.text.decode("utf-8")
                    source = node.text.decode("utf-8")
                except Exception:
                    stack.extend(node.children)
                    continue
                if len(name) >= MIN_SYMBOL_LEN:
                    kind = "class" if value_node.type == "class_expression" else "function"
                    results.append(
                        {
                            "name": name,
                            "kind": kind,
                            "start_line": start_line + node.start_point[0],
                            "end_line": start_line + node.end_point[0],
                            "content": source[:MAX_SNIPPET_CHARS],
                        }
                    )
        if node.type in _COMPONENT_BOUNDARY_TYPES:
            continue
        stack.extend(node.children)
    return results


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
    ],
    "tsx": [
        re.compile(r"(?:import|export)\s+[^'\"`]*?\s+from\s+['\"]([^'\"]+)['\"]"),
        re.compile(r"(?:import|require)\(\s*['\"]([^'\"]+)['\"]\s*\)"),
        re.compile(r"import\s+['\"]([^'\"]+)['\"]"),
    ],
    "python": [
        re.compile(r"^\s*import\s+([\w.]+)", re.M),
        re.compile(r"^\s*from\s+([\w.]+)\s+import", re.M),
    ],
    "java": [re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)", re.M)],
    "kotlin": [re.compile(r"^\s*import\s+([\w.]+)", re.M)],
    "c": [re.compile(r'#include\s*"([^"]+)"')],
    "cpp": [re.compile(r'#include\s*"([^"]+)"')],
    "rust": [
        re.compile(r"^\s*use\s+([\w:]+)", re.M),
        re.compile(r"^\s*mod\s+([\w]+);", re.M),
    ],
    "csharp": [re.compile(r"^\s*using\s+([\w.]+)\s*;", re.M)],
    "ruby": [re.compile(r"^\s*require(?:_relative)?\s+['\"]([^'\"]+)['\"]", re.M)],
}


def _extract_import_refs(language: str, content: str) -> list[str]:
    refs: list[str] = []
    for pattern in _IMPORT_PATTERNS.get(language, []):
        for match in pattern.finditer(content):
            refs.append(match.group(1).strip())
    return refs


def _resolve_import(
    ref: str,
    source_file: str,
    repo_files: set[str],
    language: str,
) -> str | None:
    """Best-effort resolution of an import/module reference to a repo file."""
    if not ref:
        return None
    base = os.path.dirname(source_file)
    candidates: list[str] = []

    if ref.startswith("."):
        if language in ("javascript", "typescript", "tsx"):
            for suffix in (
                "",
                ".js",
                ".jsx",
                ".ts",
                ".tsx",
                ".mjs",
                ".cjs",
                "/index.js",
                "/index.jsx",
                "/index.ts",
                "/index.tsx",
            ):
                candidates.append(os.path.normpath(os.path.join(base, ref + suffix)))
        elif language == "python":
            dots = len(ref) - len(ref.lstrip("."))
            parts = [p for p in ref.split(".") if p]
            pkg = base
            for _ in range(dots - 1):
                pkg = os.path.dirname(pkg)
            if parts:
                mod = "/".join(parts)
                candidates.append(os.path.join(pkg, mod + ".py"))
                candidates.append(os.path.join(pkg, mod, "__init__.py"))
            else:
                candidates.append(os.path.join(pkg, "__init__.py"))
        elif language == "ruby":
            candidates.append(os.path.normpath(os.path.join(base, ref + ".rb")))
        else:
            candidates.append(os.path.normpath(os.path.join(base, ref)))
    else:
        if language in ("c", "cpp"):
            # relative include (may be same-dir or relative to the source file)
            candidates.append(os.path.normpath(os.path.join(base, ref)))
            candidates.append(ref)
        normalized = ref.replace(".", "/")
        if language == "python":
            candidates.extend([f"{normalized}.py", f"{normalized}/__init__.py"])
        elif language in ("java", "kotlin"):
            ext = ".java" if language == "java" else ".kt"
            candidates.append(f"{normalized}{ext}")
            candidates.append(f"src/main/java/{normalized}{ext}")
            candidates.append(f"src/main/kotlin/{normalized}{ext}")
        elif language == "rust":
            mod = ref.replace("::", "/").replace("crate/", "")
            if mod.count("/") >= 1:
                mod = "/".join(mod.split("/")[:-1])
            candidates.extend([f"src/{mod}.rs", f"src/{mod}/mod.rs"])
        elif language == "csharp":
            candidates.append(f"{normalized}/")
        elif language == "ruby":
            candidates.extend([f"{normalized}.rb", f"lib/{normalized}.rb"])
        elif language in ("javascript", "typescript", "tsx", "go"):
            return None  # bare specifiers are external packages

    for cand in candidates:
        if not cand:
            continue
        if cand in repo_files:
            return cand
        for rf in repo_files:
            if rf.endswith(cand) or rf == cand:
                return rf
    return None


def build_repo_graph(repo_name: str) -> dict[str, Any]:
    """Build a symbol graph for a repo from its AST chunks in Qdrant.

    Nodes: one per file plus one per AST entity (class/function/method/...).
    Edges:
      - `defines`: entity -> the file it is defined in
      - `used_in`: entity -> another file whose chunk text references its name
      - `uses`:    entity -> entity it references (same or other file)
      - `imports`: file -> file, resolved from per-language import statements

    Symbol references are found by parsing each chunk's code with tree-sitter and
    linking a symbol only when its name appears as an identifier in another
    chunk's code. File-level `imports` edges are added by best-effort resolution
    of import/module/include/require statements across all supported languages.
    """
    chunks = _load_repo_chunks(repo_name)
    return _build_graph_from_chunks(repo_name, chunks)


def build_repo_graph_from_chunks(repo_name: str, chunks: list[Any]) -> dict[str, Any]:
    """Build a symbol graph directly from in-memory chunks (used during ingestion)."""
    return _build_graph_from_chunks(repo_name, chunks)


def _build_graph_from_chunks(repo_name: str, chunks: list[Any]) -> dict[str, Any]:
    ast_chunks = [
        c
        for c in chunks
        if c.chunk_source == "ast" and c.symbol and len(c.symbol) >= MIN_SYMBOL_LEN
    ]

    file_nodes: dict[str, dict[str, Any]] = {}
    sym_nodes: dict[str, dict[str, Any]] = {}

    for chunk in chunks:
        file_key = f"file:{chunk.file_path}"
        file_nodes.setdefault(
            file_key,
            {
                "id": file_key,
                "label": chunk.file_path,
                "kind": "file",
                "file": chunk.file_path,
                "language": chunk.language,
            },
        )

    for chunk in ast_chunks:
        sym_key = f"sym:{chunk.file_path}:{chunk.symbol}"
        existing = sym_nodes.get(sym_key)
        if existing is None:
            sym_nodes[sym_key] = {
                "id": sym_key,
                "label": chunk.symbol,
                "kind": _kind(chunk.node_type),
                "node_type": chunk.node_type,
                "file": chunk.file_path,
                "language": chunk.language,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "content": chunk.content[:MAX_SNIPPET_CHARS],
            }
        elif len(chunk.content) > len(existing["content"]):
            existing["content"] = chunk.content[:MAX_SNIPPET_CHARS]
            existing["start_line"] = min(existing["start_line"], chunk.start_line)
            existing["end_line"] = max(existing["end_line"], chunk.end_line)

    for chunk in chunks:
        if chunk.chunk_source == "ast" or chunk.language not in _JS_TS_LANGS:
            continue
        for decl in _js_component_declarations(chunk.language, chunk.content, chunk.start_line):
            sym_key = f"sym:{chunk.file_path}:{decl['name']}"
            if sym_key in sym_nodes:
                continue
            sym_nodes[sym_key] = {
                "id": sym_key,
                "label": decl["name"],
                "kind": decl["kind"],
                "node_type": "variable_declarator",
                "file": chunk.file_path,
                "language": chunk.language,
                "start_line": decl["start_line"],
                "end_line": decl["end_line"],
                "content": decl["content"],
            }

    sym_def_files: dict[str, set[str]] = {}
    for node in sym_nodes.values():
        sym_def_files.setdefault(node["label"], set()).add(node["file"])

    symbol_set = set(sym_def_files.keys())

    edge_set: set[tuple[str, str, str]] = set()

    for node in sym_nodes.values():
        edge_set.add((node["id"], f"file:{node['file']}", "defines"))

    def _add_references(
        language: str,
        content: str,
        source_file: str,
        source_sym_key: str | None,
    ) -> None:
        if not symbol_set:
            return
        idents = _identifiers_for_content(language, content)
        if not idents:
            return
        for name in idents & symbol_set:
            for def_file in sym_def_files.get(name, ()):
                target_sym = f"sym:{def_file}:{name}"
                if target_sym in sym_nodes:
                    if source_sym_key is not None and target_sym != source_sym_key:
                        edge_set.add((source_sym_key, target_sym, "uses"))
                    if def_file != source_file:
                        edge_set.add((target_sym, f"file:{source_file}", "used_in"))

    for chunk in ast_chunks:
        sym_key = f"sym:{chunk.file_path}:{chunk.symbol}"
        _add_references(chunk.language, chunk.content, chunk.file_path, sym_key)

    for chunk in chunks:
        if chunk.chunk_source == "ast":
            continue
        _add_references(chunk.language, chunk.content, chunk.file_path, None)

    repo_files = {f.file_path for f in chunks}
    for chunk in chunks:
        for ref in _extract_import_refs(chunk.language, chunk.content):
            target = _resolve_import(ref, chunk.file_path, repo_files, chunk.language)
            if target and target != chunk.file_path:
                edge_set.add((f"file:{chunk.file_path}", f"file:{target}", "imports"))

    node_ids = set(file_nodes) | set(sym_nodes)

    edges = [
        {"source": s, "target": t, "type": etype}
        for s, t, etype in sorted(edge_set)
        if s != t and s in node_ids and t in node_ids
    ]

    return {
        "repo": repo_name,
        "nodes": list(file_nodes.values()) + list(sym_nodes.values()),
        "edges": edges,
    }
