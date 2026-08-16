"""
Golden-set construction for the evaluation harness.

Ground truth is span-based: each item pairs a natural-language query with the
(file, line-range) of the code entity it targets. Span-based ground truth is
comparable across chunking strategies (naive token chunks vs AST chunks), so a
single golden set evaluates every pipeline setup (S1-S4).

The build pipeline:
1. Sample representative AST entities (functions/classes/methods carrying
   ``qualified_name``) from a repo's chunks via :func:`select_entities`.
2. Paraphrase each entity's code into a natural developer question with the
   symbol name hidden via :func:`paraphrase_entity` (DeepSeek, one call per
   entity).
3. Cache the result as committed JSON via :func:`save_golden_set` /
   :func:`load_golden_set`.
"""

import json
import logging
import math
import random
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from prompts import (
    GOLDEN_PARAPHRASE_FORCE_HIDE_SYSTEM_PROMPT,
    GOLDEN_PARAPHRASE_SYSTEM_PROMPT,
    golden_paraphrase_user_prompt,
)
from chunking.chunk_model import CodeChunk
from rag.llm_client import LLMClient

logger = logging.getLogger(__name__)

# AST node types that represent named, evaluable code entities.
_ENTITY_NODE_TYPES = frozenset(
    {
        "function_definition",
        "class_definition",
        "function_declaration",
        "class_declaration",
        "interface_declaration",
        "method_definition",
        "method_declaration",
        "function_item",
        "struct_item",
        "impl_item",
        "type_declaration",
        "object_declaration",
        "class_specifier",
        "class",
        "module",
        "method",
    }
)

_MIN_ENTITY_LINES = 3
_MAX_ENTITY_LINES = 200

_MIN_SYMBOL_LEN_FOR_LEAK = 4


@dataclass(frozen=True)
class GoldenEntity:
    """A sampled code entity and the span that identifies it as ground truth."""

    repo_hash: str
    file_path: str
    start_line: int
    end_line: int
    symbol: str
    qualified_name: str
    language: str
    content: str


@dataclass(frozen=True)
class GoldenItem:
    """One evaluation case: a query plus its ground-truth code span."""

    id: str
    query: str
    repo_hash: str
    file_path: str
    start_line: int
    end_line: int
    symbol: str
    qualified_name: str
    language: str


def select_entities(
    chunks: list[CodeChunk],
    n: int = 20,
    seed: int = 42,
    max_per_file: int = 3,
) -> list[GoldenEntity]:
    """Sample ``n`` representative AST entities from a repo's chunks.

    Filters to named AST entity chunks (``chunk_source == "ast"``, a
    ``qualified_name``, and an entity node type), dedupes by
    ``(file_path, qualified_name)``, drops degenerate spans (too short or too
    large), balances coverage across files via deterministic round-robin (at
    most ``max_per_file`` per file), then shuffles with a fixed seed.
    """
    candidates: dict[tuple[str, str], CodeChunk] = {}
    for chunk in chunks:
        if chunk.chunk_source != "ast":
            continue
        if not chunk.qualified_name or not chunk.symbol:
            continue
        if chunk.node_type not in _ENTITY_NODE_TYPES:
            continue
        span = chunk.end_line - chunk.start_line + 1
        if span < _MIN_ENTITY_LINES or span > _MAX_ENTITY_LINES:
            continue
        key = (chunk.file_path, chunk.qualified_name)
        candidates.setdefault(key, chunk)

    sorted_chunks = sorted(
        candidates.values(), key=lambda c: (c.file_path, c.start_line)
    )

    by_file: dict[str, list[CodeChunk]] = {}
    for chunk in sorted_chunks:
        by_file.setdefault(chunk.file_path, []).append(chunk)

    # Relax the per-file cap when few files would otherwise starve ``n``.
    n_files = len(by_file)
    if n_files:
        effective_max = max(max_per_file, math.ceil(n / n_files))
    else:
        effective_max = max_per_file

    selected: list[CodeChunk] = []
    used: dict[str, int] = {f: 0 for f in by_file}
    exhausted: set[str] = set()

    while len(selected) < n and len(exhausted) < len(by_file):
        progressed = False
        for f in sorted(by_file):
            if f in exhausted or len(selected) >= n:
                continue
            idx = used[f]
            if idx >= effective_max or idx >= len(by_file[f]):
                exhausted.add(f)
                continue
            selected.append(by_file[f][idx])
            used[f] = idx + 1
            progressed = True
            if len(selected) >= n:
                break
        if not progressed:
            break

    rng = random.Random(seed)
    rng.shuffle(selected)

    return [
        GoldenEntity(
            repo_hash=chunk.repo_hash or "",
            file_path=chunk.file_path,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            symbol=chunk.symbol,
            qualified_name=chunk.qualified_name,
            language=chunk.language,
            content=chunk.content,
        )
        for chunk in selected[:n]
    ]


def paraphrase_prompt(
    entity: GoldenEntity, force_hide: bool = False
) -> list[dict[str, str]]:
    """Build the DeepSeek messages that paraphrase an entity into a question."""
    system = (
        GOLDEN_PARAPHRASE_FORCE_HIDE_SYSTEM_PROMPT
        if force_hide
        else GOLDEN_PARAPHRASE_SYSTEM_PROMPT
    )
    user = golden_paraphrase_user_prompt(
        language=entity.language,
        file_path=entity.file_path,
        start_line=entity.start_line,
        end_line=entity.end_line,
        content=entity.content,
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def paraphrase_entity(
    entity: GoldenEntity, llm: LLMClient, force_hide: bool = False
) -> str:
    """Ask the LLM for a natural developer question about ``entity``."""
    response = llm.generate(paraphrase_prompt(entity, force_hide))
    return response.text.strip()


def query_leaks_symbol(query: str, entity: GoldenEntity) -> bool:
    """True iff the query reveals the entity's symbol or qualified-name part.

    A query that names the target symbol makes retrieval trivially easy and
    inflates the metrics, so leaked items are retried/dropped. Symbols shorter
    than ``_MIN_SYMBOL_LEN_FOR_LEAK`` chars are ignored to avoid false positives.
    """
    query_lower = query.lower()
    tokens: list[str] = []
    for name in (entity.symbol, entity.qualified_name):
        if not name:
            continue
        tokens.extend(part for part in name.split(".") if part)
    for token in tokens:
        if len(token) < _MIN_SYMBOL_LEN_FOR_LEAK:
            continue
        if re.search(rf"\b{re.escape(token.lower())}\b", query_lower):
            return True
    return False


def build_golden_set(
    entities: list[GoldenEntity],
    llm: LLMClient,
    id_prefix: str = "item",
    max_retries: int = 1,
) -> list[GoldenItem]:
    """Paraphrase every entity into a query and return the golden set.

    Queries that still leak the symbol name after one forced rewrite are dropped
    (logged) so the golden set stays hard for retrieval.
    """
    items: list[GoldenItem] = []
    for index, entity in enumerate(entities, start=1):
        query = paraphrase_entity(entity, llm)
        for attempt in range(max_retries + 1):
            if not query_leaks_symbol(query, entity):
                break
            if attempt < max_retries:
                logger.info(
                    "golden_item_leaked_retry id=%s symbol=%s", index, entity.symbol
                )
                query = paraphrase_entity(entity, llm, force_hide=True)

        if query_leaks_symbol(query, entity):
            logger.warning(
                "golden_item_leaked_dropped id=%s symbol=%s query=%s",
                index,
                entity.symbol,
                query[:100],
            )
            continue

        items.append(
            GoldenItem(
                id=f"{id_prefix}-{len(items) + 1}",
                query=query,
                repo_hash=entity.repo_hash,
                file_path=entity.file_path,
                start_line=entity.start_line,
                end_line=entity.end_line,
                symbol=entity.symbol,
                qualified_name=entity.qualified_name,
                language=entity.language,
            )
        )
        logger.info(
            "golden_item_generated id=%s file=%s q=%s",
            items[-1].id,
            entity.file_path,
            query[:80],
        )
    return items


def save_golden_set(items: list[GoldenItem], path: str | Path) -> None:
    """Persist the golden set as JSON (parent dirs created)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(item) for item in items]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("golden_set_saved path=%s count=%d", path, len(items))


def load_golden_set(path: str | Path) -> list[GoldenItem]:
    """Load a golden set previously saved by :func:`save_golden_set`."""
    path = Path(path)
    payload: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return [GoldenItem(**row) for row in payload]
