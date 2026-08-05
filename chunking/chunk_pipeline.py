"""
Chunking pipeline

Routes files to:
- AST chunker (for supported languages)
- Text chunker (for config/doc files)
Returns chunks directly — no pickle saves, no LLM summaries.
"""

import traceback
import logging
from typing import List, Dict

from chunking.ast_chunker import ASTChunker
from chunking.chunk_model import CodeChunk
from chunking.text_chunker import TextChunker


logger = logging.getLogger(__name__)


class ChunkPipeline:
    def __init__(self):
        self.ast_chunker = ASTChunker()
        self.text_chunker = TextChunker()

    def chunk_repository(self, files_metadata: List[Dict]) -> List[CodeChunk]:
        all_chunks: List[CodeChunk] = []
        files = list(files_metadata)

        if not files:
            return all_chunks

        for file_metadata in files:
            processing_type = file_metadata.get("processing_type", "text")

            try:
                if processing_type == "ast":
                    chunks = self.ast_chunker.chunk_file(file_metadata)
                else:
                    chunks = self.text_chunker.chunk_file(file_metadata)

                all_chunks.extend(chunks)

            except Exception:
                traceback.print_exc()
                continue

        logger.info("stage=chunk_done total_chunks=%d", len(all_chunks))
        return all_chunks
