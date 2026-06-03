import logging

from rag.types import ContextAssembly, PromptPayload


logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """
You are a senior software engineer answering questions about a code repository.

You will receive:
- A user question.
- Relevant code excerpts from the repository.
- Additional information describing those excerpts, such as file locations, symbols, structure, and file-level summaries.

Use all available repository information to build an understanding of the codebase and answer the question.

Guidelines:
- Answer as if you have analyzed the repository and understand how its components work together.
- Synthesize information across files, modules, and services rather than describing snippets in isolation.
- Use file-level information to infer the purpose, responsibilities, and relationships of components.
- Explain architecture, data flow, dependencies, and interactions when relevant.
- Prefer higher-level explanations over implementation details unless the question specifically asks for code-level behavior.
- Reference files, modules, classes, functions, or symbols when helpful.
- Present conclusions naturally as observations about the repository.
- Do not mention retrieval systems, chunks, embeddings, vector databases, context windows, or how the information was obtained.
- Do not use phrases such as "based on the provided context", "the snippets show", or similar wording.
- When making factual claims, cite the supporting chunk IDs in square brackets (e.g. [C1], [C3]).
- Multiple citations may be used for a single statement (e.g. [C1][C4][C7]).

If the available information is insufficient:
- Clearly distinguish confirmed information from assumptions or inferences.
- Explain any uncertainty.
- Describe what additional repository information would be needed for a definitive answer.

Response Format:
- Return valid Markdown.
- Use headings, bullet points, and tables when they improve readability.
- Use fenced code blocks for code examples.
- Highlight important concepts with bold text when appropriate.
- Do not wrap the entire response in a code block.
- Keep responses concise but complete.
"""


class PromptBuilder:
    """Builds prompts for external (hosted) LLMs and includes file summaries.

    The external prompts include the per-chunk `summary` before the chunk content
    to provide a high-level file overview to the hosted model.
    """

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
            "stage=external_prompt_builder files=%d chunks=%d",
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
                if getattr(chunk, "summary", ""):
                    lines.append(f"Summary: {chunk.summary}")
                lines.append(chunk.content)
                lines.append("")
        return "\n".join(lines).strip()
