import uuid
from pathlib import Path
from typing import List
from chunking.chunk_model import CodeChunk

CHUNK_SIZE = 400
CHUNK_OVERLAP = 50

class TextChunker:
    """
    Chunk plain text or non-AST files using simple token-based splitting.
    """

    def chunk_file(self, file_metadata: dict) -> List[CodeChunk]:

        file_path = file_metadata["absolute_path"]
        relative_path = file_metadata["file_path"]
        language = file_metadata.get("language", "unknown")
        repo = file_metadata.get("repo", "unknown")
        extension = Path(file_path).suffix.lower()

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception:
            return []

        tokens = text.split()
        chunks: List[CodeChunk] = []

        start = 0
        while start < len(tokens):
            end = start + CHUNK_SIZE
            chunk_tokens = tokens[start:end]
            chunk_text = " ".join(chunk_tokens)

            start_line, end_line = self._estimate_lines(text, chunk_text)

            chunk = CodeChunk(
                chunk_id=str(uuid.uuid4()),
                repo=repo,
                file_path=relative_path,
                absolute_path=file_path,
                extension=extension,
                chunk_source="text",
                language=language,
                symbol="document_section",
                node_type="text_block",
                start_line=start_line,
                end_line=end_line,
                content=chunk_text,
            )

            chunks.append(chunk)

            start += CHUNK_SIZE - CHUNK_OVERLAP

        return chunks

    @staticmethod
    def _estimate_lines(full_text: str, chunk_text: str) -> tuple[int, int]:
        """
        Estimate start and end line numbers of a chunk within the full text.
        """
        start_index = full_text.find(chunk_text)
        if start_index == -1:
            return 1, 1

        start_line = full_text[:start_index].count("\n") + 1
        end_line = start_line + chunk_text.count("\n")
        return start_line, end_line