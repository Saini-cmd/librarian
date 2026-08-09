from dataclasses import dataclass

@dataclass
class CodeChunk:
    chunk_id: str
    repo_url: str
    file_path: str
    absolute_path: str
    extension: str

    # chunk metadata
    chunk_source: str

    # code metadata
    language: str
    symbol: str
    node_type: str

    # location
    start_line: int
    end_line: int

    # content
    content: str

    # commit identity (per-commit scoping)
    repo_hash: str | None = None

    # symbol-graph metadata (graph-only; not part of embed text)
    # qualified_name = dotted ancestor chain + own symbol (e.g. "Walker.walk");
    # parent_symbol = nearest named enclosing symbol (e.g. "Walker"), "" when none.
    qualified_name: str = ""
    parent_symbol: str = ""