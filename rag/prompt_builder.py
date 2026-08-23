import logging

from core.prompts import (
    RAG_CONTEXT_CHUNK_HEADER,
    RAG_CONTEXT_FILE_HEADER,
    RAG_CONTEXT_SUMMARY,
    RAG_MEMORY_GUIDANCE,
    RAG_SYSTEM_PROMPT,
    rag_user_prompt,
)
from rag.types import ContextAssembly, PromptPayload
from summarization.summary_store import SummaryStore


logger = logging.getLogger(__name__)


class PromptBuilder:
    """Builds prompts from RAG context, conversation history, and long-term memory."""

    def build(
        self,
        query: str,
        context: ContextAssembly,
        repo_hash: str | None = None,
        history: list[dict[str, str]] | None = None,
        memory_texts: list[str] | None = None,
    ) -> PromptPayload:
        repo_names = sorted({item.chunk.repo_url for item in context.chunks if item.chunk.repo_url})
        repo_hint = ", ".join(repo_names) if repo_names else "unknown"

        summaries = None
        if repo_hash:
            loaded = SummaryStore.load(repo_hash)
            if loaded:
                summaries = loaded

        context_text = self._format_context(context, summaries)
        memory_texts = memory_texts or []

        system_prompt = RAG_SYSTEM_PROMPT
        if memory_texts:
            system_prompt = f"{RAG_SYSTEM_PROMPT}\n\n{RAG_MEMORY_GUIDANCE}"

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for turn in history or []:
            role = turn.get("role")
            if role not in ("user", "assistant"):
                continue
            messages.append({"role": role, "content": turn.get("content", "")})

        user_prompt = rag_user_prompt(repo_hint, context_text, memory_texts, query)
        messages.append({"role": "user", "content": user_prompt})

        logger.info(
            "stage=prompt_builder files=%d chunks=%d history=%d memory=%d",
            len(context.grouped_by_file),
            len(context.chunks),
            len(messages) - 2,
            len(memory_texts),
        )
        return PromptPayload(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            context_text=context_text,
            messages=messages,
        )

    @staticmethod
    def _format_context(context: ContextAssembly, summaries: dict[str, str] | None = None) -> str:
        lines: list[str] = []
        for file_path, items in context.grouped_by_file.items():
            lines.append(RAG_CONTEXT_FILE_HEADER.format(file_path=file_path))
            summary = (summaries or {}).get(file_path)
            if summary:
                lines.append(RAG_CONTEXT_SUMMARY.format(summary=summary))
            for item in items:
                chunk = item.chunk
                lines.append(
                    RAG_CONTEXT_CHUNK_HEADER.format(
                        citation_id=item.citation_id,
                        symbol=chunk.symbol or "-",
                        language=chunk.language,
                        start_line=chunk.start_line,
                        end_line=chunk.end_line,
                    )
                )
                lines.append(chunk.content)
                lines.append("")
        return "\n".join(lines).strip()
