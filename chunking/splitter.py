from uuid import uuid4
from typing import List

import tiktoken

from chunking.chunk_model import CodeChunk


DEFAULT_MAX_TOKENS = 512
_ENCODING = "cl100k_base"


class TokenSplitter:

    def __init__(self, max_tokens: int = DEFAULT_MAX_TOKENS):
        self.tokenizer = tiktoken.get_encoding(_ENCODING)
        self.max_tokens = max_tokens

    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text))

    def split_to_chunks(
        self,
        src: str,
        repo: str,
        file_path: str,
        absolute_path: str,
        extension: str,
        language: str,
        chunk_source: str = "text",
        start_line: int = 1,
    ) -> List[CodeChunk]:
        if not src.strip():
            return []

        lines = src.split("\n")
        current_lines: list[str] = []
        current_tokens = 0
        split_start = start_line
        chunks: List[CodeChunk] = []

        def flush():
            chunk_text = "\n".join(current_lines)
            chunks.append(CodeChunk(
                chunk_id=str(uuid4()),
                repo=repo,
                file_path=file_path,
                absolute_path=absolute_path,
                extension=extension,
                chunk_source=chunk_source,
                language=language,
                symbol="",
                node_type="",
                start_line=split_start,
                end_line=split_start + len(current_lines) - 1,
                content=chunk_text,
            ))

        for line in lines:
            line_tokens = self.count_tokens(line) + 1

            if current_tokens + line_tokens > self.max_tokens and current_lines:
                flush()
                split_start += len(current_lines)
                current_lines = []
                current_tokens = 0

            current_lines.append(line)
            current_tokens += line_tokens

        if current_lines:
            flush()

        return chunks
