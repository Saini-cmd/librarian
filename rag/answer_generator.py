import logging
import re
from dataclasses import replace

from rag.context_builder import ContextBuilder
from rag.llm_client import LLMClient
from rag.prompt_builder import PromptBuilder
from rag.types import AnswerResult, Citation, ContextAssembly, RetrievedChunk


logger = logging.getLogger(__name__)
_CITATION_PATTERN = re.compile(r"\[(C\d+)\]")


class AnswerGenerator:
    """End-to-end answer generator: context -> prompt -> LLM -> citation mapping."""

    def __init__(
        self,
        context_builder: ContextBuilder | None = None,
        prompt_builder: PromptBuilder | None = None,
        llm_client: LLMClient | None = None,
    ):
        self.context_builder = context_builder or ContextBuilder(max_chunks=8, token_budget=14000)
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.llm_client = llm_client or LLMClient()

    def generate(
        self,
        query: str,
        retrieved_chunks: list[RetrievedChunk | dict],
        stream: bool = False,
        repo_hash: str | None = None,
    ) -> AnswerResult:
        logger.info("stage=answer_generation_start retrieved=%d", len(retrieved_chunks))

        context = self.context_builder.build(retrieved_chunks)
        prompt_payload = self.prompt_builder.build(query=query, context=context, repo_hash=repo_hash)
        llm_response = self.llm_client.generate(prompt_payload.messages, stream=stream)

        citations = self._map_citations(llm_response.text, context, repo_hash)

        logger.info(
            "stage=answer_generation_done context_chunks=%d citations=%d",
            len(context.chunks),
            len(citations),
        )

        return AnswerResult(
            query=query,
            answer=llm_response.text,
            citations=citations,
            context_chunks=context.chunks,
            llm_model=llm_response.model,
        )

    @staticmethod
    def _map_citations(answer: str, context: ContextAssembly, repo_hash: str | None = None) -> list[Citation]:
        citation_ids = _CITATION_PATTERN.findall(answer)

        if not citation_ids:
            return []

        unique_ids = list(dict.fromkeys(citation_ids))
        citations = [context.citations[cid] for cid in unique_ids if cid in context.citations]
        if repo_hash:
            citations = [replace(c, repo_hash=repo_hash) for c in citations]
        return citations
