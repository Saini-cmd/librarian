import logging
import re

from rag.local.context_builder import ContextBuilder
from rag.local.llm.ollama_client import OllamaClient
from rag.local.prompt_builder import PromptBuilder
from rag.types import AnswerResult, Citation, ContextAssembly, RetrievedChunk


logger = logging.getLogger(__name__)
_CITATION_PATTERN = re.compile(r"\[(C\d+)\]")


class AnswerGenerator:
    """End-to-end answer generator: context -> prompt -> LLM -> citation mapping."""

    def __init__(
        self,
        context_builder: ContextBuilder | None = None,
        prompt_builder: PromptBuilder | None = None,
        llm_client: OllamaClient | None = None,
    ):
        self.context_builder = context_builder or ContextBuilder(max_chunks=8, token_budget=14000)
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.llm_client = llm_client or OllamaClient()

    def generate(
        self,
        query: str,
        retrieved_chunks: list[RetrievedChunk | dict],
        stream: bool = False,
    ) -> AnswerResult:
        logger.info("stage=answer_generation_start retrieved=%d", len(retrieved_chunks))

        context = self.context_builder.build(retrieved_chunks)
        prompt_payload = self.prompt_builder.build(query=query, context=context)
        llm_response = self.llm_client.generate(prompt_payload.messages, stream=stream)

        citations = self._map_citations(llm_response.text, context)
        answer_text = self._append_citation_fallback(llm_response.text, citations)

        logger.info(
            "stage=answer_generation_done context_chunks=%d citations=%d",
            len(context.chunks),
            len(citations),
        )

        return AnswerResult(
            query=query,
            answer=answer_text,
            citations=citations,
            context_chunks=context.chunks,
            llm_model=llm_response.model,
        )

    def generate_many(
        self,
        items: list[tuple[str, list[RetrievedChunk | dict]]],
        stream: bool = False,
    ) -> list[AnswerResult]:
        return [self.generate(query=q, retrieved_chunks=chunks, stream=stream) for q, chunks in items]

    @staticmethod
    def _map_citations(answer: str, context: ContextAssembly) -> list[Citation]:
        citation_ids = _CITATION_PATTERN.findall(answer)

        if citation_ids:
            unique_ids = list(dict.fromkeys(citation_ids))
            return [context.citations[cid] for cid in unique_ids if cid in context.citations]

        # Fallback for traceability: expose all context citations when model omitted inline references.
        return list(context.citations.values())

    @staticmethod
    def _append_citation_fallback(answer: str, citations: list[Citation]) -> str:
        if not citations:
            return answer

        if _CITATION_PATTERN.search(answer):
            return answer

        source_lines = [
            f"[{citation.citation_id}] {citation.file_path}:{citation.start_line}-{citation.end_line}"
            for citation in citations
        ]
        return f"{answer}\n\nSources:\n" + "\n".join(source_lines)
