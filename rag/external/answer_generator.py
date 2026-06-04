import logging
import re
import os  # Add this import for environment variables

from rag.external.context_builder import ContextBuilder
from rag.external.prompt_builder import PromptBuilder
from rag.external.llm.deepseek_client import DeepSeekClient
from rag.types import AnswerResult, Citation, ContextAssembly, RetrievedChunk, LLMResponse


logger = logging.getLogger(__name__)
_CITATION_PATTERN = re.compile(r"\[(C\d+)\]")

# Check if debug mode is enabled via environment variable
DEBUG_PROMPTS = os.getenv("DEBUG_PROMPTS", "true").lower() == "true"  # Default to True for testing


class AnswerGenerator:
    """External answer generator using hosted LLM (DeepSeek).

    Matches the interface of `rag.local.answer_generator.AnswerGenerator` so callers
    can swap implementations without changes.
    """

    def __init__(
        self,
        context_builder: ContextBuilder | None = None,
        prompt_builder: PromptBuilder | None = None,
        llm_client: DeepSeekClient | None = None,
    ):
        self.context_builder = context_builder or ContextBuilder(max_chunks=8, token_budget=14000)
        # Pass debug flag to PromptBuilder
        self.prompt_builder = prompt_builder or PromptBuilder(debug=DEBUG_PROMPTS)
        self.llm_client = llm_client or DeepSeekClient()
        
        if DEBUG_PROMPTS:
            print("\n" + "=" * 80)
            print("🚀 ANSWER GENERATOR INITIALIZED")
            print(f"   Debug mode: {DEBUG_PROMPTS}")
            print(f"   Max chunks: {self.context_builder.max_chunks}")
            print(f"   Token budget: {self.context_builder.token_budget}")
            print("=" * 80 + "\n")

    def generate(
        self,
        query: str,
        retrieved_chunks: list[RetrievedChunk | dict],
        stream: bool = False,
    ) -> AnswerResult:
        logger.info("stage=external_answer_generation_start retrieved=%d", len(retrieved_chunks))

        if DEBUG_PROMPTS:
            print("\n" + "🔥" * 40)
            print("GENERATING ANSWER FOR QUERY:")
            print("🔥" * 40)
            print(f"Query: {query}")
            print(f"Number of retrieved chunks: {len(retrieved_chunks)}")
            print("🔥" * 40)

        context = self.context_builder.build(retrieved_chunks)
        
        if DEBUG_PROMPTS:
            print(f"\n📊 Context built:")
            print(f"   - Unique files: {len(context.grouped_by_file)}")
            print(f"   - Total chunks in context: {len(context.chunks)}")
            print(f"   - Citations available: {len(context.citations)}")

        prompt_payload = self.prompt_builder.build(query=query, context=context)
        
        if DEBUG_PROMPTS:
            print("\n🤖 Calling LLM with prompt...")
            print(f"   - System prompt length: {len(prompt_payload.system_prompt)} chars")
            print(f"   - User prompt length: {len(prompt_payload.user_prompt)} chars")
            print(f"   - Total messages: {len(prompt_payload.messages)}")
        
        llm_response: LLMResponse = self.llm_client.generate(prompt_payload.messages, stream=stream)

        citations = self._map_citations(llm_response.text, context)
        answer_text = self._append_citation_fallback(llm_response.text, citations)

        if DEBUG_PROMPTS:
            print("\n" + "✅" * 40)
            print("ANSWER GENERATED:")
            print("✅" * 40)
            print(f"Answer length: {len(answer_text)} chars")
            print(f"Citations found: {len(citations)}")
            print("\n--- FIRST 500 CHARS OF ANSWER ---")
            print(answer_text[:500])
            if len(answer_text) > 500:
                print("... [truncated]")
            print("✅" * 40 + "\n")

        logger.info(
            "stage=external_answer_generation_done context_chunks=%d citations=%d",
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