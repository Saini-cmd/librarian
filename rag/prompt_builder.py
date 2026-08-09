import logging

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

MEMORY_GUIDANCE = (
    "The conversation history and long-term memory below provide context about previous "
    "questions and answers. They are not citable and may reference an earlier version of "
    "the code — when they conflict with the retrieved context, trust the retrieved context."
)


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

        system_prompt = SYSTEM_PROMPT
        if memory_texts:
            system_prompt = f"{SYSTEM_PROMPT}\n\n{MEMORY_GUIDANCE}"

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for turn in history or []:
            role = turn.get("role")
            if role not in ("user", "assistant"):
                continue
            messages.append({"role": role, "content": turn.get("content", "")})

        user_prompt = self._build_user_prompt(repo_hint, context_text, memory_texts, query)
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
    def _build_user_prompt(
        repo_hint: str,
        context_text: str,
        memory_texts: list[str],
        query: str,
    ) -> str:
        parts = [f"Repository scope: {repo_hint}"]
        if memory_texts:
            parts.append("Long-term memory:\n" + "\n\n".join(memory_texts))
        parts.append("Retrieved context:\n" + context_text)
        parts.append(f"User query:\n{query}")
        return "\n\n".join(parts)

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
