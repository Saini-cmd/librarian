"""
Constants used in the ingestion pipeline.
Includes supported file extensions and directories/files to ignore
during repository scanning.
"""

# -------------------------------------------------------------------
# Supported File Extensions
# Maps file extension → programming/config language
# -------------------------------------------------------------------

# -------------------------------------------------------------------
# AST PARSABLE LANGUAGES
# These will go through Tree-sitter AST chunking
# -------------------------------------------------------------------

AST_SUPPORTED_EXTENSIONS = {

    # Python
    ".py": "python",
    ".pyi": "python",

    # JavaScript / TypeScript
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",

    # JVM
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",

    # C / C++
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",

    # Systems languages
    ".rs": "rust",
    ".go": "go",

    # Microsoft
    ".cs": "csharp",

    # Backend
    ".rb": "ruby",

}


# -------------------------------------------------------------------
# TEXT BASED FILES
# These will use simple text chunking later
# -------------------------------------------------------------------

TEXT_SUPPORTED_EXTENSIONS = {

    # Infrastructure / Config
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",

    # Web
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",

    # Documentation
    ".md": "markdown",
    ".rst": "markdown",

    # Structured data
    ".json": "json",
    ".xml": "xml",
}


# -------------------------------------------------------------------
# Directories to Ignore During Scanning
# These usually contain dependencies, caches, or build artifacts
# -------------------------------------------------------------------

IGNORED_DIRS = {

    # Git
    ".git",
    ".github",

    # Python
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    "venv",
    ".venv",
    "env",

    # Node.js
    "node_modules",
    ".next",
    ".nuxt",
    ".turbo",

    # Build Outputs
    "build",
    "dist",
    "out",
    "release",
    "debug",

    # JVM / Java
    ".gradle",
    "target",

    # Go
    "vendor",

    # C / C++
    "cmake-build-debug",
    "cmake-build-release",

    # IDE / Editors
    ".idea",
    ".vscode",

    # OS files
    ".DS_Store",

    # Coverage / Reports
    "coverage",
    "htmlcov",

    # Docker / Infrastructure
    ".docker",
    ".terraform",

    # Logs / Temporary
    "logs",
    "tmp",
    "temp",
}


# -------------------------------------------------------------------
# File Patterns to Ignore
# Non-code assets and binary files
# -------------------------------------------------------------------

IGNORED_FILE_PATTERNS = {
    ".lock",
    ".log",

    # Images
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",

    # Documents
    ".pdf",

    # Archives
    ".zip",
    ".tar",
    ".gz",
}