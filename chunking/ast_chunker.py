"""
AST-based semantic chunking using Tree-sitter
Produces CodeChunk objects
"""

from chunking.ast_config import AST_CONFIG
from chunking.splitter import TokenSplitter
from chunking.parser_manager import ParserManager
from chunking.chunk_model import CodeChunk
from chunking.text_chunker import TextChunker
from typing import List

# Identifier-family node types used as declaration names (C/C++ declarators).
_IDENTIFIER_TYPES = {
    "identifier",
    "field_identifier",
    "type_identifier",
    "qualified_identifier",
    "operator_name",
}


def _node_text(node) -> str | None:
    try:
        return node.text.decode("utf-8")
    except Exception:
        return None


def _first_child_of_type(node, types: set):
    """First direct *named* child whose type is in `types` (document order)."""
    for child in node.named_children:
        if child.type in types:
            return child
    return None


def _descendant_of_type(node, node_type: str) -> None:
    """First descendant of `node_type` in depth-first document order."""
    if node.type == node_type:
        return node
    for child in node.named_children:
        found = _descendant_of_type(child, node_type)
        if found is not None:
            return found
    return None


def _c_cpp_function_name(node) -> str | None:
    """C/C++ function_definition: name lives in the declarator subtree."""
    decl = _descendant_of_type(node, "function_declarator")
    if decl is None:
        return None
    name_node = _first_child_of_type(decl, _IDENTIFIER_TYPES)
    return _node_text(name_node) if name_node is not None else None


def _go_type_name(node) -> str | None:
    """Go type_declaration: name is type_spec's type_identifier."""
    spec = _first_child_of_type(node, {"type_spec"})
    if spec is None:
        return None
    name_node = _first_child_of_type(spec, {"type_identifier"})
    return _node_text(name_node) if name_node is not None else None


def _ruby_class_module_name(node) -> str | None:
    """Ruby class/module: name is a constant (possibly in scope_resolution)."""
    first = _first_child_of_type(node, {"constant", "scope_resolution"})
    if first is None:
        return None
    if first.type == "scope_resolution":
        consts = [c for c in first.named_children if c.type == "constant"]
        return _node_text(consts[-1]) if consts else None
    return _node_text(first)


def _ruby_method_name(node) -> str | None:
    """Ruby method: name is the first identifier child."""
    name_node = _first_child_of_type(node, {"identifier"})
    return _node_text(name_node) if name_node is not None else None


def _rust_impl_symbol(node) -> str | None:
    """Rust impl_item: symbol from the target type.

    `impl User`      -> "User"
    `impl Fly for U` -> "U::Fly" (type::trait, distinct from the type node).
    """
    type_ids = [c for c in node.named_children if c.type == "type_identifier"]
    if len(type_ids) == 1:
        return _node_text(type_ids[0])
    if len(type_ids) >= 2:
        type_name = _node_text(type_ids[-1])
        trait_name = _node_text(type_ids[0])
        if type_name and trait_name:
            return f"{type_name}::{trait_name}"
    return None


def node_name(node, language: str) -> str | None:
    """Best-effort name for any AST node (declarations and named containers).

    Tries the generic `name` field first (covers every previously-working
    language), then language-specific extraction for node types whose name is
    nested elsewhere (C/C++ functions, Go types, Ruby class/module/method,
    Rust impls). Returns None when the node carries no recognizable name.
    """
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return _node_text(name_node)

    if language in ("c", "cpp") and node.type == "function_definition":
        return _c_cpp_function_name(node)
    if language == "go" and node.type == "type_declaration":
        return _go_type_name(node)
    if language == "ruby":
        if node.type in ("class", "module"):
            return _ruby_class_module_name(node)
        if node.type == "method":
            return _ruby_method_name(node)
    if language == "rust":
        if node.type == "impl_item":
            return _rust_impl_symbol(node)
    return None


def collect_tree_nodes(node, wanted_nodes, language: str, parents=None) -> List:
    """Recursively collect AST nodes of interest.

    Returns a list of `(node, parent_chain)` where `parent_chain` is the dotted
    list of named ancestors (including the node's own name, if any). Recursion
    stops at the first wanted node, so nested wanted nodes are subsumed into
    their nearest wanted ancestor's chunk.
    """
    tree_nodes = []
    parents = list(parents or [])

    name = node_name(node, language)
    if name:
        parents.append(name)

    if node.type in wanted_nodes:
        tree_nodes.append((node, parents))
    else:
        for child in node.children:
            tree_nodes.extend(collect_tree_nodes(child, wanted_nodes, language, parents))

    return tree_nodes


class ASTChunker:

    def __init__(self, max_tokens=420):
        self.parser_manager = ParserManager()
        self.splitter = TokenSplitter(max_tokens=max_tokens)

    def chunk_file(self, file_metadata: dict) -> List[CodeChunk]:

        file_path = file_metadata["absolute_path"]
        language = file_metadata["language"]
        extension = file_metadata["extension"]
        repo_url = file_metadata.get("repo_url", "")
        repo_hash = file_metadata.get("repo_hash")

        lang_config = AST_CONFIG.get(language)
        if not lang_config:
            # fallback to text chunker
            text_chunker = TextChunker()
            return text_chunker.chunk_file(file_metadata)

        # Read file safely
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            file_content = f.read()

        # Parse AST — .tsx files use the JSX-aware `tsx` grammar while keeping
        # the `language` label stable (typescript) so filters/metadata don't change.
        parser_language = "tsx" if language == "typescript" and extension == ".tsx" else language
        parser = self.parser_manager.get_parser(parser_language)
        tree = parser.parse(bytes(file_content, "utf-8"))
        root_node = tree.root_node

        chunks: List[CodeChunk] = []

        # Collect AST nodes of interest (with their named-ancestor chain)
        collected = collect_tree_nodes(root_node, lang_config["wanted_nodes"], language)
        collected.sort(key=lambda item: item[0].start_byte)

        cursor = 0
        line = root_node.start_point[0] + 1  # 1-indexed

        for node, parents in collected:

            # Handle gap before this node
            if cursor < node.start_byte:
                gap_text = file_content[cursor:node.start_byte]
                gap_chunks = self.splitter.split_to_chunks(
                    src=gap_text,
                    repo_url=repo_url,
                    file_path=file_metadata["file_path"],
                    absolute_path=file_path,
                    extension=extension,
                    language=language,
                    chunk_source="text",
                    start_line=line,
                    repo_hash=repo_hash,
                )
                chunks.extend(gap_chunks)

            # Extract node content
            node_text = file_content[node.start_byte:node.end_byte]
            node_line = node.start_point[0] + 1  # 1-indexed

            # Split large AST node if needed
            node_chunks = self.splitter.split_to_chunks(
                src=node_text,
                repo_url=repo_url,
                file_path=file_metadata["file_path"],
                absolute_path=file_path,
                extension=extension,
                language=language,
                chunk_source="ast",
                start_line=node_line,
                repo_hash=repo_hash,
            )

            # Symbol + qualified identity from the named-ancestor chain
            symbol = parents[-1] if parents else None
            parent_symbol = parents[-2] if len(parents) >= 2 else ""
            qualified_name = ".".join(parents) if parents else ""

            # Assign symbol, node_type, and graph metadata
            for chunk in node_chunks:
                chunk.symbol = symbol
                chunk.node_type = node.type
                chunk.qualified_name = qualified_name
                chunk.parent_symbol = parent_symbol

            chunks.extend(node_chunks)

            cursor = node.end_byte
            line = node.end_point[0] + 1

        # Handle remaining tail content
        if cursor < len(file_content):
            tail_text = file_content[cursor:]
            tail_chunks = self.splitter.split_to_chunks(
                src=tail_text,
                repo_url=repo_url,
                file_path=file_metadata["file_path"],
                absolute_path=file_path,
                extension=extension,
                language=language,
                chunk_source="text",
                start_line=line,
                repo_hash=repo_hash,
            )
            chunks.extend(tail_chunks)

        return chunks
