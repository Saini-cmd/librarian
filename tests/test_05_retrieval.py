from bootstrap import ensure_repo_root

ensure_repo_root()

from retrieval.retrieval_pipeline import RetrievalPipeline
from retrieval.query_expander import QueryExpander


QUERIES = [
    "how is authentication implemented in lynko?",
]


def main():
    pipeline = RetrievalPipeline()
    expander = QueryExpander()

    for query in QUERIES:
        print("\n" + "=" * 100)
        print(f"Query: {query}")
        print(f"Expanded Query: {expander.expand(query)}")
        print("=" * 100)

        results = pipeline.retrieve(query)
        print(f"Retrieved {len(results)} final chunks")

        for i, item in enumerate(results, start=1):
            chunk = item["chunk"]
            score = item["score"]
            rrf_score = item["rrf_score"]
            vector_score = item["vector_score"]
            bm25_score = item["bm25_score"]

            print("-" * 100)
            print(f"Rank: {i}")
            print(f"Score: {score:.6f}")
            print(f"RRF: {rrf_score:.6f}")
            print(f"Vector: {vector_score if vector_score is not None else 'N/A'}")
            print(f"BM25: {bm25_score if bm25_score is not None else 'N/A'}")
            print(f"Repo: {chunk.repo}")
            print(f"File: {chunk.file_path}")
            print(f"Language: {chunk.language}")
            print(f"Symbol: {chunk.symbol}")
            print(f"Lines: {chunk.start_line}-{chunk.end_line}")
            print("\nContent Preview:")
            print(chunk.content)


if __name__ == "__main__":
    main()
