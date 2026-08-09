"""Graph-side entity synthesis from text chunks (RAG-freeze).

Entity types that are NOT AST-chunked (enums, structs, type aliases, consts,
vars, traits, modules, records, JS/TS components) live inside text chunks —
the gap/remainder text the AST chunker leaves alone. This module parses text
chunks with tree-sitter and synthesizes graph entity dicts from them, so the
graph is complete WITHOUT adding those entity types to the embedding corpus.

Synthesized entities follow the same node schema as AST entities:
`{name, kind, qualified_name, parent, node_type, start_line, end_line, content}`.
Nested declarations (e.g. Rust trait methods) are qualified under their
synthesized container (`Fly.fly` with `parent="Fly"`); the frontend renders
containment structurally by nesting entities inside file nodes (no `contains`
edge type). `.tsx` files (chunk `language="typescript"`, `extension=".tsx"`) are
parsed with the JSX-aware `tsx` grammar.
"""

from typing import Any

from chunking.parser_manager import ParserManager

MAX_SNIPPET_CHARS = 4000
MIN_SYMBOL_LEN = 2

_JS_TS_LANGS = {"javascript", "typescript", "tsx"}

# Non-wanted declaration node types to synthesize, per language: node_type -> kind.
_SYNTH_DECLARATIONS: dict[str, dict[str, str]] = {
    "typescript": {"type_alias_declaration": "type", "enum_declaration": "enum"},
    "tsx": {"type_alias_declaration": "type", "enum_declaration": "enum"},
    "java": {"enum_declaration": "enum", "record_declaration": "record"},
    "c": {"struct_specifier": "struct", "enum_specifier": "enum", "type_definition": "type"},
    "cpp": {
        "struct_specifier": "struct",
        "enum_specifier": "enum",
        "union_specifier": "union",
        "type_definition": "type",
        "namespace_definition": "module",
    },
    "rust": {
        "trait_item": "trait",
        "enum_item": "enum",
        "type_item": "type",
        "const_item": "const",
        "static_item": "const",
        "union_item": "struct",
        "mod_item": "module",
        "function_signature_item": "method",
    },
    "go": {"const_spec": "const", "var_spec": "var"},
    "csharp": {
        "enum_declaration": "enum",
        "record_declaration": "record",
        "struct_declaration": "struct",
        "delegate_declaration": "type",
    },
}

# Module-level const/var statement node types to synthesize, per language.
_SYNTH_CONST_NODES: dict[str, set[str]] = {
    "python": {"expression_statement"},
    "ruby": {"assignment"},
    "kotlin": {"property_declaration"},
}

# Stop the walk at function bodies / blocks / literals (module-level synthesis).
_BOUNDARY_TYPES = {
    "function_definition",
    "function_declaration",
    "method_definition",
    "arrow_function",
    "function_expression",
    "generator_function",
    "statement_block",
    "block",
    "compound_statement",
    "template_string",
    "string_literal",
    "comment",
}

# Synthesized declarations that nest other declarations (traits -> methods,
# modules/namespaces -> items). Leaf declarations don't descend.
_CONTAINER_TYPES = {"trait_item", "mod_item", "namespace_definition"}

_COMPONENT_VALUE_TYPES = {
    "arrow_function",
    "function_expression",
    "generator_function",
    "class_expression",
}

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


def _node_text(node) -> str | None:
    try:
        return node.text.decode("utf-8")
    except Exception:
        return None


def _first_child_of_type(node, types: set):
    for child in node.named_children:
        if child.type in types:
            return child
    return None


def _contains_jsx(node) -> bool:
    stack = [node]
    while stack:
        cur = stack.pop()
        if cur.type.startswith("jsx_"):
            return True
        stack.extend(cur.named_children)
    return False


def _extract_synth_name(node, node_type: str) -> str | None:
    """Name for a synthesized declaration node (first `name` field, else per-type child)."""
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return _node_text(name_node)
    if node_type in ("type_alias_declaration", "trait_item", "enum_item", "union_item"):
        return _node_text(_first_child_of_type(node, {"type_identifier"}))
    if node_type in (
        "enum_declaration",
        "record_declaration",
        "struct_declaration",
        "delegate_declaration",
        "const_item",
        "static_item",
        "mod_item",
        "struct_specifier",
        "enum_specifier",
        "union_specifier",
        "function_signature_item",
    ):
        return _node_text(_first_child_of_type(node, {"identifier", "type_identifier"}))
    if node_type == "namespace_definition":
        return _node_text(_first_child_of_type(node, {"namespace_identifier"}))
    if node_type == "type_definition":
        return _node_text(_first_child_of_type(node, {"type_identifier"}))
    if node_type in ("const_spec", "var_spec"):
        return _node_text(_first_child_of_type(node, {"identifier"}))
    return None


def _js_ts_declarator(node, start_line: int, container_q: str, container_parent: str) -> dict | None:
    """JS/TS `const X = ...`: function/class expr -> component/function/class,
    anything else -> const."""
    name_node = node.child_by_field_name("name")
    value_node = node.child_by_field_name("value")
    if name_node is None or name_node.type not in ("identifier", "property_identifier"):
        return None
    name = _node_text(name_node)
    if not name or len(name) < MIN_SYMBOL_LEN:
        return None
    if value_node is not None and value_node.type in _COMPONENT_VALUE_TYPES:
        if value_node.type == "class_expression":
            kind = "class"
        elif name[0].isupper() or _contains_jsx(value_node):
            kind = "component"
        else:
            kind = "function"
    else:
        kind = "const"
    qualified = f"{container_q}.{name}" if container_q else name
    return {
        "name": name,
        "kind": kind,
        "qualified_name": qualified,
        "parent": container_parent,
        "node_type": "variable_declarator",
        "start_line": start_line + node.start_point[0],
        "end_line": start_line + node.end_point[0],
        "content": _node_text(node)[:MAX_SNIPPET_CHARS],
    }


def _const_entry(language: str, node, start_line: int, container_q: str, container_parent: str) -> dict | None:
    """Module-level const/var from an assignment/property statement."""
    name: str | None = None
    kind = "const"
    if language == "python":
        assign = _first_child_of_type(node, {"assignment", "annotated_assignment"})
        if assign is not None:
            name_node = _first_child_of_type(assign, {"identifier"})
            name = _node_text(name_node) if name_node else None
            if name and not name.isupper():
                kind = "var"
    elif language == "ruby":
        name_node = _first_child_of_type(node, {"constant"})
        name = _node_text(name_node) if name_node else None
    elif language == "kotlin":
        vdecl = _first_child_of_type(node, {"variable_declaration"})
        if vdecl is not None:
            name_node = _first_child_of_type(vdecl, {"identifier"})
            name = _node_text(name_node) if name_node else None
    if not name or len(name) < MIN_SYMBOL_LEN:
        return None
    qualified = f"{container_q}.{name}" if container_q else name
    return {
        "name": name,
        "kind": kind,
        "qualified_name": qualified,
        "parent": container_parent,
        "node_type": node.type,
        "start_line": start_line + node.start_point[0],
        "end_line": start_line + node.end_point[0],
        "content": _node_text(node)[:MAX_SNIPPET_CHARS],
    }


def _walk(
    language: str,
    node,
    start_line: int,
    container_q: str,
    container_parent: str,
    out: list[dict],
) -> None:
    node_type = node.type
    decl_kind = _SYNTH_DECLARATIONS.get(language, {}).get(node_type)
    if decl_kind is not None:
        name = _extract_synth_name(node, node_type)
        if name and len(name) >= MIN_SYMBOL_LEN:
            qualified = f"{container_q}.{name}" if container_q else name
            out.append(
                {
                    "name": name,
                    "kind": decl_kind,
                    "qualified_name": qualified,
                    "parent": container_parent,
                    "node_type": node_type,
                    "start_line": start_line + node.start_point[0],
                    "end_line": start_line + node.end_point[0],
                    "content": _node_text(node)[:MAX_SNIPPET_CHARS],
                }
            )
            if node_type in _CONTAINER_TYPES:
                for child in node.named_children:
                    _walk(language, child, start_line, qualified, name, out)
            return
        # unnamed container (anonymous struct/enum) -> descend without adding
        for child in node.named_children:
            _walk(language, child, start_line, container_q, container_parent, out)
        return

    if language in _SYNTH_CONST_NODES and node_type in _SYNTH_CONST_NODES[language]:
        entry = _const_entry(language, node, start_line, container_q, container_parent)
        if entry is not None:
            out.append(entry)

    if language in _JS_TS_LANGS and node_type == "variable_declarator":
        entry = _js_ts_declarator(node, start_line, container_q, container_parent)
        if entry is not None:
            out.append(entry)

    if node_type in _BOUNDARY_TYPES:
        return
    for child in node.children:
        _walk(language, child, start_line, container_q, container_parent, out)


def synthesize_entities(
    language: str,
    extension: str,
    content: str,
    start_line: int,
) -> list[dict]:
    """Synthesize graph entity dicts from a text chunk's code.

    `.tsx` files are parsed with the `tsx` grammar (their chunk `language` is
    `typescript`, but the extension disambiguates JSX). Parse errors and
    unsupported languages yield nothing.
    """
    if not language or not content:
        return []
    parse_lang = "tsx" if language == "typescript" and extension == ".tsx" else language
    tree = _parse(parse_lang, content)
    if tree is None:
        return []
    out: list[dict] = []
    _walk(language, tree.root_node, start_line, "", "", out)
    return out
