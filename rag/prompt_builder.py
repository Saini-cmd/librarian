import logging

from rag.types import ContextAssembly, PromptPayload


logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are a senior software engineer assisting with repository-level code understanding.
Use only the provided retrieved context.
If information is missing from context, say so explicitly.
Prefer code-grounded explanations and concrete references.
Do not hallucinate APIs, files, or behavior not present in context.
Respond concisely in technical language.
When making claims, cite relevant chunk IDs in square brackets, e.g. [C1], [C2]."""


class PromptBuilder:
    """Builds deterministic prompts for repository-aware answer generation."""

    def build(self, query: str, context: ContextAssembly) -> PromptPayload:
        repo_names = sorted({item.chunk.repo for item in context.chunks if item.chunk.repo})
        repo_hint = ", ".join(repo_names) if repo_names else "unknown"

        context_text = self._format_context(context)
        user_prompt = (
            f"Repository scope: {repo_hint}\n\n"
            f"Retrieved context:\n{context_text}\n\n"
            f"User query:\n{query}"
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        logger.info(
            "stage=prompt_builder files=%d chunks=%d",
            len(context.grouped_by_file),
            len(context.chunks),
        )
        return PromptPayload(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            context_text=context_text,
            messages=messages,
        )

    @staticmethod
    def _format_context(context: ContextAssembly) -> str:
        lines: list[str] = []
        for file_path, items in context.grouped_by_file.items():
            lines.append(f"## File: {file_path}")
            for item in items:
                chunk = item.chunk
                lines.append(
                    f"[{item.citation_id}] symbol={chunk.symbol or '-'} "
                    f"lang={chunk.language} lines={chunk.start_line}-{chunk.end_line}"
                )
                lines.append(chunk.content)
                lines.append("")
        return "\n".join(lines).strip()
