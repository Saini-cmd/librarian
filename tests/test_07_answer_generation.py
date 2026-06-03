from bootstrap import ensure_repo_root

ensure_repo_root()

from retrieval.retrieval_pipeline import RetrievalPipeline
from rag.local.answer_generator import AnswerGenerator


QUERIES = [
    # "How is authentication implemented in this repo?",
    "can you give the overview of the repo? what is it about and what are the main components?",
]


def main():
    retrieval = RetrievalPipeline()
    answer_generator = AnswerGenerator()

    for query in QUERIES:
        print("\n" + "=" * 100)
        print(f"Query: {query}")
        print("=" * 100)

        retrieved = retrieval.retrieve(query)
        print(f"Retrieved chunks: {len(retrieved)}")

        result = answer_generator.generate(query=query, retrieved_chunks=retrieved)

        print("\n" + "-" * 100)
        print(f"Model: {result.llm_model}")
        print("-" * 100)
        print("Answer:\n")
        print(result.answer)

        print("\nCitations:")
        for citation in result.citations:
            print(
                f"[{citation.citation_id}] "
                f"{citation.file_path}:{citation.start_line}-{citation.end_line} "
                f"symbol={citation.symbol} lang={citation.language}"
            )


if __name__ == "__main__":
    main()
