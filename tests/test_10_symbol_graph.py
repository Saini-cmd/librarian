"""Regression harness for the symbol-graph overhaul (see PLAN.md).

Builds graphs from synthetic per-language snippets through the REAL chunker
(ASTChunker) + graph builder, and asserts the current node/edge behavior.
Assertions marked `KNOWN_BUG (Phase N)` document defects the plan's later
phases will fix — flip those to the corrected expectation as each phase lands.
Runs as a standalone script (no pytest), like the other test_XX files.
"""

from bootstrap import ensure_repo_root

ensure_repo_root()

import os
import sys
import tempfile

from chunking.ast_chunker import ASTChunker
from chunking.chunk_model import CodeChunk
from symbol_graph.graph_builder import GRAPH_VERSION, build_repo_graph_from_chunks
from symbol_graph.imports import extract_import_refs, resolve_import
from vector_store.indexer import chunk_from_payload

PASS = 0
FAIL = 0


def check(cond: bool, msg: str) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {msg}")
    else:
        FAIL += 1
        print(f"  FAIL {msg}")


def entity_labels(graph) -> list[tuple[str, str]]:
    return sorted((n["label"], n["kind"]) for n in graph["nodes"] if n["kind"] != "file")


def chunk_snippet(code: str, language: str, ext: str, name: str, tempdir: str) -> list[CodeChunk]:
    """Run the real AST chunker on a snippet written to a temp file."""
    path = os.path.join(tempdir, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(code)
    if not ext.startswith("."):
        ext = "." + ext  # match file_scanner's `suffix.lower()` (e.g. ".tsx")
    meta = {
        "absolute_path": path,
        "file_path": name,
        "language": language,
        "extension": ext,
        "repo_url": "https://example.com/repo",
        "repo_hash": "h",
        "processing_type": "ast",
    }
    return ASTChunker().chunk_file(meta)


def mk_ast_chunk(
    path: str,
    language: str,
    symbol: str,
    node_type: str,
    start: int,
    end: int,
    content: str,
    qualified_name: str | None = None,
    parent_symbol: str = "",
) -> CodeChunk:
    return CodeChunk(
        chunk_id=f"{path}:{start}",
        repo_url="https://example.com/repo",
        file_path=path,
        absolute_path="/tmp/" + path,
        extension="",
        chunk_source="ast",
        language=language,
        symbol=symbol,
        node_type=node_type,
        start_line=start,
        end_line=end,
        content=content,
        repo_hash="h",
        qualified_name=qualified_name if qualified_name is not None else symbol,
        parent_symbol=parent_symbol,
    )


# ---- Section A: entity coverage per language (baseline) ----
# KNOWN_BUG markers: Phase 1 fixes C/C++/Ruby/Go/Rust symbol extraction; Phase 3
# adds qualified ids (methods/overloads become distinct nodes); Phase 4 adds
# graph-side synthesis for the missing entity types (enums, structs, consts...).
SAMPLES = {
    "python": ("py", "class Foo:\n    def bar(self):\n        pass\n\ndef top(x):\n    return x\n\nVALUE = 42\n"),
    "javascript": ("js", "class Foo {\n  bar() { return 1 }\n}\nfunction top(x) { return x }\nconst comp = () => 1;\nexport default Foo;\n"),
    "typescript": ("ts", "interface IFoo {\n  a: number;\n}\nenum Status { Active }\ntype Alias = string;\nclass Foo {\n  bar(): void {}\n}\nfunction top(x: number) { return x }\n"),
    "java": ("java", "public class Foo {\n  private int bar() { return 1; }\n  public static void main(String[] a) {}\n}\ninterface IFoo { void x(); }\n"),
    "kotlin": ("kt", "class Foo {\n  fun bar(): Int = 1\n}\ninterface IFoo {}\nobject Singleton {}\n"),
    "c": ("c", "int add(int a, int b) { return a+b; }\n"),
    "cpp": ("cpp", "class Foo {\n  public:\n    int bar() { return 1; }\n};\nint free_fn(int x) { return x; }\n"),
    "rust": ("rs", "pub struct User {\n    name: String,\n}\npub trait Fly { fn fly(&self); }\npub fn top(x: i32) -> i32 { x }\nimpl User {\n    pub fn new() -> Self { Self { name: String::new() } }\n}\nimpl Fly for User {\n    fn fly(&self) {}\n}\n"),
    "go": ("go", "type User struct {\n\tName string\n}\nfunc (u *User) Greet() string { return \"hi\" }\nfunc top(x int) int { return x }\n"),
    "csharp": ("cs", "public class Foo {\n  private int bar() { return 1; }\n}\npublic interface IFoo { void X(); }\npublic enum Color { Red }\n"),
    "ruby": ("rb", "class Foo\n  def bar\n    1\n  end\nend\nmodule Baz\nend\ndef top(x)\n  x\nend\n"),
    "tsx": ("tsx", "const MyButton = () => <div>hi</div>\n"),
}

# Entity nodes (label, kind) observed from the current pipeline.
# Phase 1 fixed C/C++/Ruby/Go/Rust symbol extraction; Phase 4 synthesizes the
# rich entity types (enums, structs, type aliases, consts, traits, components)
# from text chunks; methods inside classes remain subsumed (Phase 3 machinery
# is in place for when they become nodes).
EXPECTED_ENTITIES = {
    "python": [("Foo", "class"), ("VALUE", "const"), ("top", "function")],
    "javascript": [("Foo", "class"), ("comp", "function"), ("top", "function")],
    "typescript": [("Alias", "type"), ("Foo", "class"), ("IFoo", "interface"), ("Status", "enum"), ("top", "function")],
    "java": [("Foo", "class"), ("IFoo", "interface")],
    "kotlin": [("Foo", "class"), ("IFoo", "class"), ("Singleton", "class")],
    "c": [("add", "function")],
    "cpp": [("Foo", "class"), ("free_fn", "function")],
    "rust": [("Fly", "trait"), ("User", "class"), ("User::Fly", "impl"), ("fly", "method"), ("top", "function")],
    "go": [("Greet", "method"), ("User", "class"), ("top", "function")],
    "csharp": [("Color", "enum"), ("Foo", "class"), ("IFoo", "interface")],
    "ruby": [("Baz", "module"), ("Foo", "class"), ("top", "method")],
    "tsx": [("MyButton", "component")],
}


def test_entity_coverage() -> None:
    print("\n== A. Entity coverage per language (real chunker + graph builder) ==")
    td = tempfile.mkdtemp()
    for lang, (ext, code) in SAMPLES.items():
        chunks = chunk_snippet(code, lang, ext, f"s_{lang}.{ext}", td)
        g = build_repo_graph_from_chunks(lang, chunks)
        got = entity_labels(g)
        check(
            got == EXPECTED_ENTITIES[lang],
            f"{lang:12} entities {got} == {EXPECTED_ENTITIES[lang]}",
        )
        check("version" in g, f"{lang:12} graph carries version field")
        check(g["version"] == GRAPH_VERSION, f"{lang:12} version == {GRAPH_VERSION}")


def test_method_subsumption() -> None:
    print("\n== B. Method subsumption (collect_tree_nodes stops at first wanted node) ==")
    td = tempfile.mkdtemp()
    # Python method `bar` is inside the `class Foo` wanted node -> not a separate
    # entity today. KNOWN_BUG Phase 3/4: methods should become nodes (contained).
    chunks = chunk_snippet("class Foo:\n    def bar(self):\n        pass\n", "python", "py", "m.py", td)
    g = build_repo_graph_from_chunks("subsumption", chunks)
    labels = [l for l, _ in entity_labels(g)]
    check("Foo" in labels and "bar" not in labels, f"method `bar` subsumed into class chunk (labels={labels})")


def test_dedup_collapse() -> None:
    print("\n== C. Dedup by (file, qualified_name) ==")
    # Same qualified_name (unqualified) -> still collapses.
    same = [
        mk_ast_chunk("svc.ts", "typescript", "login", "method_definition", 2, 4, "  login() { return true }", qualified_name="login"),
        mk_ast_chunk("svc.ts", "typescript", "login", "method_definition", 13, 15, "  login() { return false }", qualified_name="login"),
    ]
    g = build_repo_graph_from_chunks("dedup-same", same)
    nodes = [n for n in g["nodes"] if n["kind"] != "file"]
    check(len(nodes) == 1, f"same qualified_name merges into one node ({len(nodes)} found, expected 1)")

    # Distinct qualified_name (methods in different classes) stays distinct.
    distinct = [
        mk_ast_chunk("svc.ts", "typescript", "AuthService", "class_declaration", 1, 10, "class AuthService {\n  login() { return true }\n}"),
        mk_ast_chunk("svc.ts", "typescript", "login", "method_definition", 2, 4, "  login() { return true }", qualified_name="AuthService.login", parent_symbol="AuthService"),
        mk_ast_chunk("svc.ts", "typescript", "BillingService", "class_declaration", 12, 20, "class BillingService {\n  login() { return false }\n}"),
        mk_ast_chunk("svc.ts", "typescript", "login", "method_definition", 13, 15, "  login() { return false }", qualified_name="BillingService.login", parent_symbol="BillingService"),
    ]
    g2 = build_repo_graph_from_chunks("dedup-distinct", distinct)
    nodes2 = [n for n in g2["nodes"] if n["kind"] != "file"]
    ids2 = {n["id"] for n in nodes2}
    check(len(nodes2) == 4, f"distinct qualified_name stays distinct ({len(nodes2)} nodes, expected 4)")
    check(
        "sym:svc.ts:AuthService.login" in ids2 and "sym:svc.ts:BillingService.login" in ids2,
        "both qualified `login` nodes exist",
    )


def test_name_collision_noise() -> None:
    print("\n== D. Cross-file same-name references: scoped resolution ==")
    # Phase 3: scoped resolution drops ambiguous/spurious edges (no link-to-all).
    td = tempfile.mkdtemp()
    chunks = []
    for m in [
        chunk_snippet("def shared():\n    return 1\ndef helper_a():\n    return shared()\n", "python", "py", "moda.py", td),
        chunk_snippet("def shared():\n    return 2\n", "python", "py", "modb.py", td),
    ]:
        chunks.extend(m)
    g = build_repo_graph_from_chunks("collision", chunks)
    uses = {(e["source"], e["target"]) for e in g["edges"] if e["type"] == "uses"}
    used_in = {(e["source"], e["target"]) for e in g["edges"] if e["type"] == "used_in"}
    check(
        ("sym:moda.py:helper_a", "sym:moda.py:shared") in uses,
        "helper_a -> same-file shared resolves (unambiguous)",
    )
    check(
        ("sym:moda.py:helper_a", "sym:modb.py:shared") not in uses,
        "helper_a does NOT link to unrelated modb shared",
    )
    check(
        ("sym:moda.py:shared", "sym:modb.py:shared") not in uses,
        "no self-name shared<->shared contamination",
    )
    check(
        ("sym:moda.py:shared", "file:modb.py") not in used_in,
        "no spurious moda shared 'used_in' modb.py",
    )
    check(
        ("sym:modb.py:shared", "file:moda.py") not in used_in,
        "no spurious modb shared 'used_in' moda.py",
    )
    check(len(uses) == 1, f"exactly one uses edge remains ({len(uses)})")


# ---- Section E: import extraction + resolution (Phase 2: imports overhauled) ----
REPO_FILES = {
    "src/app/main.py", "src/app/helpers.py", "src/app/__init__.py",
    "package/sub/module.py", "package/sub/__init__.py",
    "src/pages/Home.jsx", "src/shared/index.jsx", "src/pages/styles.css", "src/pages/re-export.jsx",
    "src/main/java/com/example/internal/Helper.java", "src/main/java/com/example/Constants.java",
    "src/main/kotlin/com/example/internal/Helper.kt", "src/main/kotlin/com/example/Constants.kt",
    "internal/util/util.go",
    "src/utils.rs", "src/database.rs", "src/models.rs", "src/auth.rs",
    "src/local.h", "shared/common.h", "myheader.hpp", "lib/core/core.hpp",
    "src/Project/Core/Models/Thing.cs",
    "app/models/user.rb",
}

IMPORT_CASES = [
    # (language, content, source_file, expected_refs, expected_resolutions)
    ("python", "from package.sub import thing", "src/app/main.py", ["package.sub"], ["package/sub/__init__.py"]),
    ("python", "from .helpers import foo", "src/app/main.py", [".helpers"], ["src/app/helpers.py"]),
    ("python", "import package.sub.module", "src/app/main.py", ["package.sub.module"], ["package/sub/module.py"]),
    ("python", "import app.helpers", "src/app/main.py", ["app.helpers"], ["src/app/helpers.py"]),  # src-layout package root
    ("javascript", "import { bar } from '../shared/index'", "src/pages/Home.jsx", ["../shared/index"], ["src/shared/index.jsx"]),
    ("javascript", "import React from 'react'", "src/pages/Home.jsx", ["react"], [None]),
    ("javascript", "import './styles.css'", "src/pages/Home.jsx", ["./styles.css"], ["src/pages/styles.css"]),
    ("java", "import com.example.internal.Helper;", "src/main/java/com/example/App.java", ["com.example.internal.Helper"], ["src/main/java/com/example/internal/Helper.java"]),
    ("java", "import static com.example.Constants.MAX;", "src/main/java/com/example/App.java", ["com.example.Constants.MAX"], ["src/main/java/com/example/Constants.java"]),  # member-strip
    ("kotlin", "import com.example.internal.Helper", "src/main/kotlin/com/example/App.kt", ["com.example.internal.Helper"], ["src/main/kotlin/com/example/internal/Helper.kt"]),
    ("kotlin", "import com.example.Constants.MAX", "src/main/kotlin/com/example/App.kt", ["com.example.Constants.MAX"], ["src/main/kotlin/com/example/Constants.kt"]),  # member-strip
    ("go", 'import (\n  "internal/util"\n)', "cmd/server/main.go", ["internal/util"], ["internal/util/util.go"]),  # block imports
    ("go", 'import "github.com/other/repo/x"', "cmd/server/main.go", ["github.com/other/repo/x"], [None]),  # external
    ("csharp", "using Project.Core.Models;", "src/Project/Web/Program.cs", ["Project.Core.Models"], ["src/Project/Core/Models/Thing.cs"]),  # namespace -> file
    ("csharp", "using System.Collections.Generic;", "src/Project/Web/Program.cs", ["System.Collections.Generic"], [None]),  # external
    ("rust", "mod database;\n", "src/services/user.rs", ["database"], ["src/database.rs"]),
    ("rust", "pub mod auth;\n", "src/services/user.rs", ["auth"], ["src/auth.rs"]),  # pub mod captured
    ("rust", "use crate::utils::helpers;", "src/services/user.rs", ["crate::utils::helpers"], ["src/utils.rs"]),
    ("rust", "use super::models;", "src/services/user.rs", ["super::models"], ["src/models.rs"]),  # super:: resolved
    ("c", '#include "local.h"', "src/impl/util.c", ["local.h"], ["src/local.h"]),
    ("c", '#include "../shared/common.h"', "src/impl/util.c", ["../shared/common.h"], ["shared/common.h"]),  # ../ resolution
    ("cpp", '#include <lib/core/core.hpp>', "src/impl/util.cpp", ["lib/core/core.hpp"], ["lib/core/core.hpp"]),  # angle project include
    ("ruby", "require_relative 'models/user'", "app/services/worker.rb", ["models/user"], ["app/models/user.rb"]),
    ("ruby", "require 'json'", "app/services/worker.rb", ["json"], [None]),
]


def test_imports() -> None:
    print("\n== E. Import extraction + resolution ==")
    for lang, content, src, exp_refs, exp_res in IMPORT_CASES:
        refs = extract_import_refs(lang, content)
        check(refs == exp_refs, f"{lang:10} refs {refs} == {exp_refs} ({content[:40]!r})")
        res = [resolve_import(r, src, REPO_FILES, lang) for r in refs]
        check(res == exp_res, f"{lang:10} res   {res} == {exp_res} ({content[:40]!r})")


def test_ts_aliases() -> None:
    print("\n== E2. tsconfig paths alias end-to-end ==")
    td = tempfile.mkdtemp()
    chunks = [
        c
        for snippet in [
            chunk_snippet(
                '{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}',
                "json", ".json", "tsconfig.json", td,
            ),
            chunk_snippet("export const Btn = () => 1;\n", "typescript", ".ts", "src/components/Button.tsx", td),
            chunk_snippet("import { Btn } from '@/components/Button'\nexport const App = () => Btn;\n", "typescript", ".ts", "src/App.tsx", td),
        ]
        for c in snippet
    ]
    g = build_repo_graph_from_chunks("aliases", chunks)
    imports = {e["source"]: e["target"] for e in g["edges"] if e["type"] == "imports"}
    check(
        imports.get("file:src/App.tsx") == "file:src/components/Button.tsx",
        f"@/components/Button resolves via tsconfig paths ({imports.get('file:src/App.tsx')})",
    )


def test_js_ts_synthesis() -> None:
    print("\n== F. JS/TS component/const synthesis ==")
    td = tempfile.mkdtemp()
    js = chunk_snippet("const comp = () => 1;\n", "javascript", "js", "c.js", td)
    check(("comp", "function") in entity_labels(build_repo_graph_from_chunks("js", js)), "lowercase arrow const -> function")

    jsx_const = chunk_snippet("const data = { a: 1 };\n", "javascript", "js", "d.js", td)
    check(("data", "const") in entity_labels(build_repo_graph_from_chunks("js", jsx_const)), "non-function const -> const")

    tsx = chunk_snippet("const MyButton = () => <div>hi</div>\n", "tsx", "tsx", "c.tsx", td)
    check(("MyButton", "component") in entity_labels(build_repo_graph_from_chunks("tsx", tsx)), "PascalCase JSX arrow -> component")

    # Real ingestion: .tsx files are chunked with language "typescript" but
    # extension ".tsx" — synthesis must use the JSX-aware tsx parser.
    tsx_real = chunk_snippet("const MyButton = () => <div>hi</div>\n", "typescript", "tsx", "c2.tsx", td)
    check(
        ("MyButton", "component") in entity_labels(build_repo_graph_from_chunks("typescript", tsx_real)),
        "JSX in .tsx (language typescript) synthesizes via tsx parser",
    )

    ts_jsx = chunk_snippet("const MyButton = () => <div>hi</div>\n", "typescript", "ts", "c3.ts", td)
    check(
        ("MyButton", "function") not in entity_labels(build_repo_graph_from_chunks("typescript", ts_jsx)),
        "JSX in a .ts (non-tsx) file is not synthesized",
    )


def test_qualified_identity() -> None:
    print("\n== G. qualified_name / parent_symbol + payload round-trip ==")
    td = tempfile.mkdtemp()
    # Rust trait-with-body: method gets the trait as parent.
    trait = chunk_snippet(
        "pub trait Walker {\n  fn walk(&self) {}\n}\npub fn top() {}\n", "rust", "rs", "t.rs", td
    )
    walk = [c for c in trait if c.chunk_source == "ast" and c.symbol == "walk"][0]
    top = [c for c in trait if c.chunk_source == "ast" and c.symbol == "top"][0]
    check(walk.qualified_name == "Walker.walk" and walk.parent_symbol == "Walker", f"trait method qualified {walk.qualified_name!r} parent {walk.parent_symbol!r}")
    check(top.qualified_name == "top" and top.parent_symbol == "", f"top-level qualified {top.qualified_name!r} parent {top.parent_symbol!r}")

    # Working languages keep top-level-only identity (no parent-chain pollution).
    py = chunk_snippet("class Foo:\n    pass\n\ndef top(x):\n    return x\n", "python", "py", "p.py", td)
    py_ast = [c for c in py if c.chunk_source == "ast"]
    check(
        all(c.qualified_name == c.symbol and c.parent_symbol == "" for c in py_ast),
        "python AST chunks: qualified_name == symbol, parent_symbol == ''",
    )

    # Payload round-trip preserves the new fields.
    ast_chunk = walk
    payload = {k: getattr(ast_chunk, k) for k in (
        "chunk_id", "repo_url", "repo_hash", "file_path", "absolute_path", "extension",
        "chunk_source", "language", "symbol", "node_type", "qualified_name", "parent_symbol",
        "start_line", "end_line", "content")}
    back = chunk_from_payload(payload)
    check(
        back is not None and back.qualified_name == "Walker.walk" and back.parent_symbol == "Walker",
        "chunk_from_payload round-trips qualified_name/parent_symbol",
    )

    # Old payloads without the new keys still parse (backward compatible).
    payload.pop("qualified_name")
    payload.pop("parent_symbol")
    old = chunk_from_payload(payload)
    check(
        old is not None and old.qualified_name == "" and old.parent_symbol == "",
        "old payload (no new keys) defaults to empty qualified fields",
    )


def test_scoped_resolution() -> None:
    print("\n== H. Scoped reference resolution + node schema ==")

    # Node schema: name / qualified_name / parent present; label == name.
    chunks = [mk_ast_chunk("t.rs", "rust", "top", "function_item", 1, 2, "pub fn top() {}")]
    g = build_repo_graph_from_chunks("schema", chunks)
    node = next(n for n in g["nodes"] if n["kind"] != "file")
    check(node["label"] == node["name"] == "top", f"label/name == 'top' ({node['label']!r} / {node['name']!r})")
    check(node["qualified_name"] == "top" and node["parent"] == "", f"qualified/parent on node ({node['qualified_name']!r} / {node['parent']!r})")

    # Method relabel: function_item nested under a class-like parent -> method.
    relabel = [
        mk_ast_chunk("u.rs", "rust", "User", "struct_item", 1, 1, "struct User;"),
        mk_ast_chunk("u.rs", "rust", "new", "function_item", 2, 3, "fn new() {}", qualified_name="User.new", parent_symbol="User"),
    ]
    g2 = build_repo_graph_from_chunks("relabel", relabel)
    m = next(n for n in g2["nodes"] if n["id"] == "sym:u.rs:User.new")
    check(m["kind"] == "method", f"nested fn under class -> kind method ({m['kind']})")

    # Cross-file single definition resolves via unique-global.
    cross = [
        mk_ast_chunk("a.py", "python", "shared", "function_definition", 1, 2, "def shared():\n    return 1\n"),
        mk_ast_chunk("b.py", "python", "helper_b", "function_definition", 1, 2, "def helper_b():\n    return shared()\n"),
    ]
    g3 = build_repo_graph_from_chunks("cross", cross)
    uses3 = {(e["source"], e["target"]) for e in g3["edges"] if e["type"] == "uses"}
    check(("sym:b.py:helper_b", "sym:a.py:shared") in uses3, "cross-file single def resolves (unique global)")

    # Ambiguous global (defined in 2 files, import-neither) is dropped.
    ambiguous = [
        mk_ast_chunk("a.py", "python", "shared", "function_definition", 1, 2, "def shared():\n    return 1\n"),
        mk_ast_chunk("b.py", "python", "shared", "function_definition", 1, 2, "def shared():\n    return 2\n"),
        mk_ast_chunk("c.py", "python", "caller", "function_definition", 1, 2, "def caller():\n    return shared()\n"),
    ]
    g4 = build_repo_graph_from_chunks("ambiguous", ambiguous)
    uses4 = {(e["source"], e["target"]) for e in g4["edges"] if e["type"] == "uses"}
    check(
        ("sym:c.py:caller", "sym:a.py:shared") not in uses4 and ("sym:c.py:caller", "sym:b.py:shared") not in uses4,
        "ambiguous cross-file reference dropped (precision)",
    )

    # Chain resolution: AuthService.login() -> parent-scoped method node.
    chain = [
        mk_ast_chunk("svc.ts", "typescript", "AuthService", "class_declaration", 1, 5, "class AuthService {}\n"),
        mk_ast_chunk("svc.ts", "typescript", "login", "method_definition", 2, 3, "  login() { return true }", qualified_name="AuthService.login", parent_symbol="AuthService"),
        mk_ast_chunk("main.ts", "typescript", "main", "function_declaration", 1, 2, "function main() {\n  AuthService.login()\n}"),
    ]
    g5 = build_repo_graph_from_chunks("chain", chain)
    uses5 = {(e["source"], e["target"]) for e in g5["edges"] if e["type"] == "uses"}
    check(
        ("sym:main.ts:main", "sym:svc.ts:AuthService.login") in uses5,
        "chain ref AuthService.login() resolves to parent-scoped method",
    )
    check(
        ("sym:main.ts:main", "sym:svc.ts:AuthService") in uses5,
        "chain object AuthService resolves to the class",
    )


def main() -> None:
    print(f"# test_10_symbol_graph.py — Phase 0 baseline (graph version {GRAPH_VERSION})")
    test_entity_coverage()
    test_method_subsumption()
    test_dedup_collapse()
    test_name_collision_noise()
    test_imports()
    test_ts_aliases()
    test_js_ts_synthesis()
    test_qualified_identity()
    test_scoped_resolution()
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
