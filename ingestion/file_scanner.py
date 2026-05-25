import os
from pathlib import Path

from ingestion.constants import (
    AST_SUPPORTED_EXTENSIONS,
    TEXT_SUPPORTED_EXTENSIONS,
    IGNORED_DIRS,
    IGNORED_FILE_PATTERNS,
)

MAX_FILE_SIZE = 1_000_000  # 1 MB

def get_processing_type(extension: str) -> str:

    if extension in AST_SUPPORTED_EXTENSIONS:
        return "ast"

    if extension in TEXT_SUPPORTED_EXTENSIONS:
        return "text"

    return "unknown"

class FileScanner:

    def scan_repository(self, repo_path: Path):
        """
        Scan repository and return metadata for supported files.
        """

        files_metadata = []

        for root, dirs, files in os.walk(repo_path):

            # Remove ignored directories
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]

            for file in files:

                file_path = Path(root) / file

                try:
                    extension = file_path.suffix.lower()

                    processing_type = get_processing_type(extension)

                    # Skip unsupported files
                    if processing_type == "unknown":
                        continue

                    # Skip ignored patterns
                    if extension in IGNORED_FILE_PATTERNS:
                        continue

                    # Skip very large files
                    file_size = file_path.stat().st_size
                    if file_size > MAX_FILE_SIZE:
                        continue

                    # Determine language
                    if processing_type == "ast":
                        language = AST_SUPPORTED_EXTENSIONS[extension]
                    else:
                        language = TEXT_SUPPORTED_EXTENSIONS[extension]

                    metadata = {
                        "file_path": str(file_path.relative_to(repo_path)),
                        "absolute_path": str(file_path),
                        "language": language,
                        "extension": extension,
                        "size": file_size,
                        "processing_type": processing_type
                    }

                    files_metadata.append(metadata)

                except (OSError, PermissionError):
                    continue

        return files_metadata