from tree_sitter_languages import get_language

AST_CONFIG = {
    # -------------------------
    # Python
    # -------------------------
    "python": {
        "language": lambda: get_language("python"),
        "wanted_nodes": {"function_definition", "class_definition"},
    },

    # -------------------------
    # JavaScript
    # -------------------------
    "javascript": {
        "language": lambda: get_language("javascript"),
        "wanted_nodes": {"function_declaration", "class_declaration", "method_definition"},
    },

    # -------------------------
    # TypeScript
    # -------------------------
    "typescript": {
        "language": lambda: get_language("typescript"),
        "wanted_nodes": {"function_declaration", "class_declaration", "interface_declaration", "method_definition"},
    },

    # -------------------------
    # Java
    # -------------------------
    "java": {
        "language": lambda: get_language("java"),
        "wanted_nodes": {"class_declaration", "method_declaration", "interface_declaration"},
    },

    # -------------------------
    # Kotlin
    # -------------------------
    "kotlin": {
        "language": lambda: get_language("kotlin"),
        "wanted_nodes": {"class_declaration", "function_declaration", "object_declaration", "interface_declaration"},
    },

    # -------------------------
    # C
    # -------------------------
    "c": {
        "language": lambda: get_language("c"),
        "wanted_nodes": {"function_definition"},
    },

    # -------------------------
    # C++
    # -------------------------
    "cpp": {
        "language": lambda: get_language("cpp"),
        "wanted_nodes": {"function_definition", "class_specifier"},
    },

    # -------------------------
    # Rust
    # -------------------------
    "rust": {
        "language": lambda: get_language("rust"),
        "wanted_nodes": {"function_item", "struct_item", "impl_item"},
    },

    # -------------------------
    # Go
    # -------------------------
    "go": {
        "language": lambda: get_language("go"),
        "wanted_nodes": {"function_declaration", "method_declaration", "type_declaration"},
    },

    # -------------------------
    # C#
    # -------------------------
    "csharp": {
        "language": lambda: get_language("c_sharp"),
        "wanted_nodes": {"class_declaration", "method_declaration", "interface_declaration"},
    },

    # -------------------------
    # Ruby
    # -------------------------
    "ruby": {
        "language": lambda: get_language("ruby"),
        "wanted_nodes": {"class", "module", "method"},
    },
}