import logging
from functools import lru_cache

from langchain_core.prompts import ChatPromptTemplate

from rag.types import ContextAssembly, PromptPayload
from summarization.summary_store import SummaryStore


logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are a senior software engineer assisting with repository-level code understanding.
Use only the provided retrieved context.
If information is missing from context, say so explicitly.
Prefer code-grounded explanations and concrete references.
Do not hallucinate APIs, files, or behavior not present in context.
Respond concisely in technical language.
When making claims, cite the relevant chunk IDs in square brackets, e.g. [C1], [C2].
Cite only chunks you actually reference and never invent citations; if an answer needs no grounding, do not cite."""


class PromptBuilder:
    """Builds deterministic prompts using LCEL ChatPromptTemplate."""

    def __init__(self):
        self._template = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", "Repository scope: {repo_hint}\n\nRetrieved context:\n{context_text}\n\nUser query:\n{query}"),
        ])

    def build(self, query: str, context: ContextAssembly, repo_hash: str | None = None) -> PromptPayload:
        repo_names = sorted({item.chunk.repo_url for item in context.chunks if item.chunk.repo_url})
        repo_hint = ", ".join(repo_names) if repo_names else "unknown"

        summaries = None
        if repo_hash:
            loaded = SummaryStore.load(repo_hash)
            if loaded:
                summaries = loaded

        context_text = self._format_context(context, summaries)
        lc_messages = self._template.format_messages(
            repo_hint=repo_hint, context_text=context_text, query=query
        )
        messages = [{"role": m.type, "content": m.content} for m in lc_messages]

        logger.info(
            "stage=prompt_builder files=%d chunks=%d",
            len(context.grouped_by_file),
            len(context.chunks),
        )
        return PromptPayload(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=messages[-1]["content"] if messages else "",
            context_text=context_text,
            messages=messages,
        )

    @staticmethod
    def _format_context(context: ContextAssembly, summaries: dict[str, str] | None = None) -> str:
        lines: list[str] = []
        for file_path, items in context.grouped_by_file.items():
            lines.append(f"## File: {file_path}")
            summary = (summaries or {}).get(file_path)
            if summary:
                lines.append(f"Summary: {summary}")
            for item in items:
                chunk = item.chunk
                lines.append(
                    f"[{item.citation_id}] symbol={chunk.symbol or '-'} "
                    f"lang={chunk.language} lines={chunk.start_line}-{chunk.end_line}"
                )
                lines.append(chunk.content)
                lines.append("")
        return "\n".join(lines).strip()
