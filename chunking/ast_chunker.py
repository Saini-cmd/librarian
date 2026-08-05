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

def collect_tree_nodes(node, wanted_nodes) -> List:
    """Recursively collect AST nodes of interest"""
    tree_nodes = []

    if node.type in wanted_nodes:
        tree_nodes.append(node)
    else:
        for child in node.children:
            tree_nodes.extend(collect_tree_nodes(child, wanted_nodes))

    return tree_nodes

class ASTChunker:

    def __init__(self, max_tokens=420):
        self.parser_manager = ParserManager()
        self.splitter = TokenSplitter(max_tokens=max_tokens)

    def chunk_file(self, file_metadata: dict) -> List[CodeChunk]:

        file_path = file_metadata["absolute_path"]
        language = file_metadata["language"]
        extension = file_metadata["extension"]
        repo = file_metadata.get("repo", "")

        lang_config = AST_CONFIG.get(language)
        if not lang_config:
            # fallback to text chunker
            text_chunker = TextChunker()
            return text_chunker.chunk_file(file_metadata)

        # Read file safely
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            file_content = f.read()

        # Parse AST
        parser = self.parser_manager.get_parser(language)
        tree = parser.parse(bytes(file_content, "utf-8"))
        root_node = tree.root_node

        chunks: List[CodeChunk] = []

        # Collect AST nodes of interest
        wanted_nodes = collect_tree_nodes(root_node, lang_config["wanted_nodes"])
        wanted_nodes.sort(key=lambda n: n.start_byte)

        cursor = 0
        line = root_node.start_point[0] + 1  # 1-indexed

        for node in wanted_nodes:

            # Handle gap before this node
            if cursor < node.start_byte:
                gap_text = file_content[cursor:node.start_byte]
                gap_chunks = self.splitter.split_to_chunks(
                    src=gap_text,
                    repo=repo,
                    file_path=file_metadata["file_path"],
                    absolute_path=file_path,
                    extension=extension,
                    language=language,
                    chunk_source="text",
                    start_line=line
                )
                chunks.extend(gap_chunks)

            # Extract node content
            node_text = file_content[node.start_byte:node.end_byte]
            node_line = node.start_point[0] + 1  # 1-indexed

            # Split large AST node if needed
            node_chunks = self.splitter.split_to_chunks(
                src=node_text,
                repo=repo,
                file_path=file_metadata["file_path"],
                absolute_path=file_path,
                extension=extension,
                language=language,
                chunk_source="ast",
                start_line=node_line
            )

            # Extract symbol safely
            symbol_node = node.child_by_field_name("name")
            symbol = None
            if symbol_node:
                try:
                    symbol = symbol_node.text.decode("utf-8")
                except Exception:
                    symbol = None

            # Assign symbol and node_type
            for chunk in node_chunks:
                chunk.symbol = symbol
                chunk.node_type = node.type

            chunks.extend(node_chunks)

            cursor = node.end_byte
            line = node.end_point[0] + 1

        # Handle remaining tail content
        if cursor < len(file_content):
            tail_text = file_content[cursor:]
            tail_chunks = self.splitter.split_to_chunks(
                src=tail_text,
                repo=repo,
                file_path=file_metadata["file_path"],
                absolute_path=file_path,
                extension=extension,
                language=language,
                chunk_source="text",
                start_line=line
            )
            chunks.extend(tail_chunks)

        return chunks