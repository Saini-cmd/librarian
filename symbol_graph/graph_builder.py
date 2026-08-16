from typing import Any
import threading

from qdrant_client.models import FieldCondition, Filter, MatchValue

from chunking.parser_manager import ParserManager
from symbol_graph.imports import extract_import_refs as _extract_import_refs
from symbol_graph.imports import load_ts_aliases as _load_ts_aliases
from symbol_graph.imports import resolve_import as _resolve_import
from symbol_graph.synthesis import synthesize_entities as _synthesize_entities
from vector_store.indexer import chunk_from_payload
from vector_store.qdrant_client import QdrantManager


COLLECTION_NAME = "code_chunks"
MAX_SNIPPET_CHARS = 4000
MIN_SYMBOL_LEN = 2

# Graph schema version. Bump when the graph JSON shape changes; `GET /graph`
# lazily rebuilds + persists stored graphs whose version is below this.
GRAPH_VERSION = 3

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
    "method": "method",
    "module": "module",
    "method_definition": "method",
    "method_declaration": "method",
}


def _load_repo_chunks(repo_hash: str | None = None) -> list[Any]:
    client = QdrantManager().get_client()
    chunks: list[Any] = []
    offset = None
    scroll_filter = None
    if repo_hash:
        scroll_filter = Filter(
            must=[FieldCondition(key="repo_hash", match=MatchValue(value=repo_hash))]
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
_PARSERS_LOCK = threading.Lock()


def _get_parser(language: str):
    if not language:
        return None
    with _PARSERS_LOCK:
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


def _node_text(node) -> str | None:
    try:
        return node.text.decode("utf-8")
    except Exception:
        return None


_MEMBER_ACCESS_NODE: dict[str, str | None] = {
    "javascript": "member_expression",
    "typescript": "member_expression",
    "tsx": "member_expression",
    "python": "attribute",
    "java": "field_access",
    "kotlin": "navigation_expression",
    "c": None,
    "cpp": "field_expression",
    "rust": "field_expression",
    "go": "selector_expression",
    "csharp": "member_access_expression",
    "ruby": "call",
}


def _member_chain(node, language: str) -> str | None:
    """If `node` is the field/method side of a member access, return the object
    name (e.g. `AuthService` for `AuthService.login`); else None."""
    access_type = _MEMBER_ACCESS_NODE.get(language)
    parent = node.parent
    if access_type is None or parent is None or parent.type != access_type:
        return None
    named = parent.named_children
    if len(named) < 2:
        return None
    obj = named[0]
    if not (obj.type.endswith("identifier") or obj.type == "constant"):
        return None  # object is not a simple identifier
    if node == obj:
        return None  # this identifier IS the object side
    return _node_text(obj)


def _references_for_content(
    language: str,
    content: str,
    start_line: int,
    extension: str = "",
) -> list[tuple[str, int, int, str | None]]:
    """Return `(name, line, column, chain)` for every identifier reference.

    Collects every node whose type ends with 'identifier' (identifier,
    type_identifier, field_identifier, property_identifier, method_identifier),
    plus `constant` nodes (Ruby class/module/constant references). `chain` is
    the dotted object name when the identifier is a member-access field
    (`AuthService.login`), else None. `.tsx` chunks (language `typescript`)
    are parsed with the JSX-aware `tsx` grammar via `extension`. Lines are
    absolute (chunk `start_line` offset); columns are within the chunk.
    Unsupported languages / parse errors yield nothing.
    """
    parse_lang = "tsx" if language == "typescript" and extension == ".tsx" else language
    tree = _parse(parse_lang, content)
    if tree is None:
        return []
    refs: list[tuple[str, int, int, str | None]] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type.endswith("identifier") or node.type == "constant":
            text = _node_text(node)
            if text:
                refs.append(
                    (
                        text,
                        start_line + node.start_point[0],
                        node.start_point[1],
                        _member_chain(node, parse_lang),
                    )
                )
        stack.extend(node.children)
    return refs



def build_repo_graph(repo_hash: str | None = None, repo_label: str | None = None) -> dict[str, Any]:
    """Build a symbol graph for a commit from its AST chunks in Qdrant.

    Nodes: one per file plus one per AST entity (class/function/method/...).
    Edges:
      - `used_in`:  entity -> another file whose chunk text references it
      - `uses`:     entity -> entity it references (same or other file), with
                    optional `line`/`column` of the first reference
      - `imports`:  file -> file, resolved from per-language import statements

    (File membership is NOT an edge type — `defines` was removed because the
    frontend renders it structurally by nesting each file's entities inside the
    file node; containment is likewise structural.)

    Symbol references are found by parsing each chunk's code with tree-sitter and
    resolved by scope: same-scope -> same-file -> imported module -> unique global
    match; ambiguous references are dropped (precision over recall). Qualified
    node ids (`sym:{file}:{qualified_name}`) and containment come from the chunk
    `qualified_name`/`parent_symbol` metadata added by the chunker; chunks without
    it (old payloads) fall back to bare-name ids and name-only resolution.
    File-level `imports` edges are added by best-effort resolution of
    import/module/include/require statements across all supported languages.

    `repo_hash` scopes the graph to a specific commit (retained old-commit chunks
    are excluded when set).
    """
    chunks = _load_repo_chunks(repo_hash)
    return _build_graph_from_chunks(repo_label, chunks)


def build_repo_graph_from_chunks(repo_label: str | None, chunks: list[Any]) -> dict[str, Any]:
    """Build a symbol graph directly from in-memory chunks (used during ingestion)."""
    return _build_graph_from_chunks(repo_label, chunks)


def _build_graph_from_chunks(repo_label: str | None, chunks: list[Any]) -> dict[str, Any]:
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
        qualified = chunk.qualified_name or chunk.symbol
        sym_key = f"sym:{chunk.file_path}:{qualified}"
        existing = sym_nodes.get(sym_key)
        if existing is None:
            sym_nodes[sym_key] = {
                "id": sym_key,
                "label": chunk.symbol,
                "name": chunk.symbol,
                "qualified_name": qualified,
                "parent": chunk.parent_symbol or "",
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
        if chunk.chunk_source == "ast":
            continue
        for decl in _synthesize_entities(chunk.language, chunk.extension, chunk.content, chunk.start_line):
            sym_key = f"sym:{chunk.file_path}:{decl['qualified_name']}"
            if sym_key in sym_nodes:
                continue
            sym_nodes[sym_key] = {
                "id": sym_key,
                "label": decl["name"],
                "name": decl["name"],
                "qualified_name": decl["qualified_name"],
                "parent": decl["parent"],
                "kind": decl["kind"],
                "node_type": decl["node_type"],
                "file": chunk.file_path,
                "language": chunk.language,
                "start_line": decl["start_line"],
                "end_line": decl["end_line"],
                "content": decl["content"],
            }

    # Functions nested under a class-like parent become methods.
    for node in sym_nodes.values():
        if node["node_type"] not in ("function_definition", "function_item") or not node["parent"]:
            continue
        parent_q = node["qualified_name"].rsplit(".", 1)[0] if "." in node["qualified_name"] else None
        parent_node = sym_nodes.get(f"sym:{node['file']}:{parent_q}") if parent_q else None
        if parent_node and parent_node["kind"] in ("class", "interface", "impl"):
            node["kind"] = "method"

    # Symbol index: name -> candidate definitions (for scoped resolution).
    sym_index: dict[str, list[dict[str, Any]]] = {}
    for node in sym_nodes.values():
        sym_index.setdefault(node["name"], []).append(node)

    edge_set: dict[tuple[str, str, str], dict] = {}

    def _add_edge(source: str, target: str, etype: str, **meta) -> None:
        if source != target:
            edge_set[(source, target, etype)] = meta or None  # type: ignore[assignment]

    repo_files = {f.file_path for f in chunks}
    ts_aliases = _load_ts_aliases(chunks)

    # File -> resolved import targets (used both for `imports` edges and scoping).
    imported_by_file: dict[str, set[str]] = {}
    for chunk in chunks:
        src = chunk.file_path
        for ref in _extract_import_refs(chunk.language, chunk.content):
            target = _resolve_import(ref, src, repo_files, chunk.language, ts_aliases=ts_aliases)
            if target and target != src:
                imported_by_file.setdefault(src, set()).add(target)
                _add_edge(f"file:{src}", f"file:{target}", "imports")

    def _resolve_name(
        name: str,
        chunk_file: str,
        chunk_parent: str,
        imported_files: set[str],
    ) -> dict[str, Any] | None:
        """Scoped resolution: same-scope -> same-file -> imported -> unique global."""
        candidates = sym_index.get(name)
        if not candidates:
            return None
        if chunk_parent:
            scoped = [c for c in candidates if c["file"] == chunk_file and c["parent"] == chunk_parent]
            if len(scoped) == 1:
                return scoped[0]
        same_file = [c for c in candidates if c["file"] == chunk_file]
        if len(same_file) == 1:
            return same_file[0]
        imported = [c for c in candidates if c["file"] in imported_files]
        if len(imported) == 1:
            return imported[0]
        if len(candidates) == 1:
            return candidates[0]
        return None  # ambiguous -> drop (precision over recall)

    def _resolve_ref(
        name: str,
        chain: str | None,
        chunk_file: str,
        chunk_parent: str,
        imported_files: set[str],
    ) -> dict[str, Any] | None:
        if chain:
            obj = _resolve_name(chain, chunk_file, chunk_parent, imported_files)
            if obj:
                children = [c for c in sym_index.get(name, []) if c["parent"] == obj["qualified_name"]]
                return children[0] if len(children) == 1 else None
        return _resolve_name(name, chunk_file, chunk_parent, imported_files)

    def _add_references(
        language: str,
        content: str,
        source_file: str,
        chunk_start_line: int,
        chunk_parent: str,
        source_sym_keys: list[str] | None,
        extension: str = "",
    ) -> None:
        if not sym_index:
            return
        imported_files = imported_by_file.get(source_file, set())
        for name, line, column, chain in _references_for_content(language, content, chunk_start_line, extension):
            target = _resolve_ref(name, chain, source_file, chunk_parent, imported_files)
            if target is None:
                continue
            if source_sym_keys:
                for source_sym_key in source_sym_keys:
                    if source_sym_key != target["id"]:
                        _add_edge(source_sym_key, target["id"], "uses", line=line, column=column)
            if target["file"] != source_file:
                _add_edge(target["id"], f"file:{source_file}", "used_in")

    for chunk in ast_chunks:
        sym_key = f"sym:{chunk.file_path}:{chunk.qualified_name or chunk.symbol}"
        _add_references(
            chunk.language,
            chunk.content,
            chunk.file_path,
            chunk.start_line,
            chunk.parent_symbol or "",
            [sym_key],
            chunk.extension,
        )

    for chunk in chunks:
        if chunk.chunk_source == "ast":
            continue
        # Each synthesized entity emits `uses` from its OWN declaration content
        # (not the whole text chunk, which clusters module-level consts/vars).
        for decl in _synthesize_entities(chunk.language, chunk.extension, chunk.content, chunk.start_line):
            key = f"sym:{chunk.file_path}:{decl['qualified_name']}"
            if key in sym_nodes:
                _add_references(
                    chunk.language,
                    decl["content"],
                    chunk.file_path,
                    decl["start_line"],
                    decl["parent"],
                    [key],
                    chunk.extension,
                )
        # File-level `used_in` from the chunk's own text (no source entity).
        _add_references(
            chunk.language,
            chunk.content,
            chunk.file_path,
            chunk.start_line,
            "",
            None,
            chunk.extension,
        )

    node_ids = set(file_nodes) | set(sym_nodes)

    edges = [
        {"source": s, "target": t, "type": etype, **(meta or {})}
        for (s, t, etype), meta in sorted(edge_set.items())
        if s != t and s in node_ids and t in node_ids
    ]

    return {
        "repo": repo_label,
        "version": GRAPH_VERSION,
        "nodes": list(file_nodes.values()) + list(sym_nodes.values()),
        "edges": edges,
    }
