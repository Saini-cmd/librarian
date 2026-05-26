"""
Chunking pipeline

Routes files to:
- AST chunker
- Text chunker
"""

import traceback
import os
import pickle
from pathlib import Path
from dataclasses import asdict
from chunking.ast_chunker import ASTChunker
from chunking.text_chunker import TextChunker
from chunking.chunk_model import CodeChunk
from typing import List, Dict
from tqdm import tqdm


class ChunkPipeline:

    def __init__(self):
        self.ast_chunker = ASTChunker()
        self.text_chunker = TextChunker()

    def chunk_repository(self, files_metadata: List[Dict], repo_name: str) -> List[CodeChunk]:

        all_chunks: List[CodeChunk] = []

        for i, file_metadata in enumerate(tqdm(files_metadata, desc="Chunking files")):

            processing_type = file_metadata.get("processing_type", "text")
            file_path = file_metadata.get("file_path", "unknown")

            try:
                if processing_type == "ast":
                    chunks = self.ast_chunker.chunk_file(file_metadata)
                    all_chunks.extend(chunks)

                elif processing_type == "text":
                    chunks = self.text_chunker.chunk_file(file_metadata)
                    all_chunks.extend(chunks)

            except Exception:
                traceback.print_exc()
                continue

        self._save_chunks(repo_name, all_chunks)

        return all_chunks

    def _save_chunks(self, repo_name: str, chunks: List[CodeChunk]):

        try:
            chunks_dir = Path("data/chunks")
            chunks_dir.mkdir(parents=True, exist_ok=True)

            output_path = chunks_dir / f"{repo_name}.pkl"
            temp_path = output_path.with_suffix(".pkl.tmp")

            serializable_chunks = [asdict(chunk) for chunk in chunks]

            with open(temp_path, "wb") as f:
                pickle.dump(serializable_chunks, f)

            temp_path.replace(output_path)

            print(f"\nSaved {len(chunks)} chunks → {output_path}")

        except Exception:
            print("Failed to save chunks")
            traceback.print_exc()