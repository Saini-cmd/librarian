"""
Parser Manager

Loads and manages Tree-sitter languages
for AST chunking.
"""

from tree_sitter import Parser, Language
from tree_sitter_python import language as python_language
from tree_sitter_typescript import language_typescript, language_tsx
from tree_sitter_javascript import language as javascript_language
from tree_sitter_java import language as java_language
from tree_sitter_kotlin import language as kotlin_language
from tree_sitter_go import language as go_language
from tree_sitter_rust import language as rust_language
from tree_sitter_c import language as c_language
from tree_sitter_cpp import language as cpp_language
from tree_sitter_c_sharp import language as csharp_language
from tree_sitter_ruby import language as ruby_language

class ParserManager:

    def __init__(self):
        self.languages = {
            "python": Language(python_language()),
            "javascript": Language(javascript_language()),
            "typescript": Language(language_typescript()),
            "tsx": Language(language_tsx()),
            "java": Language(java_language()),
            "kotlin": Language(kotlin_language()),
            "go": Language(go_language()),
            "rust": Language(rust_language()),
            "c": Language(c_language()),
            "cpp": Language(cpp_language()),
            "csharp": Language(csharp_language()),
            "ruby": Language(ruby_language()),
        }

    def get_language(self, language_name: str) -> Language:
        language = self.languages.get(language_name)
        if not language:
            raise ValueError(f"Language not supported: {language_name}")
        return language
    
    def get_parser(self, language_name: str):
        language = self.get_language(language_name)
        return Parser(language)