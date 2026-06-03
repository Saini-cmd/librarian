from bootstrap import ensure_repo_root

ensure_repo_root()

from ingestion.ingestion_pipeline import IngestionPipeline
from chunking.chunk_pipeline import ChunkPipeline


REPOS = [
    # Python
    "https://github.com/fastapi/fastapi",

    # JavaScript
    # "https://github.com/expressjs/express",

    # TypeScript
    # "https://github.com/axios/axios",

    # Go
    # "https://github.com/gin-gonic/gin",

    # Rust
    # "https://github.com/BurntSushi/ripgrep",

    # Java
    # "https://github.com/spring-projects/spring-petclinic",

    # Kotlin
    # "https://github.com/KotlinBy/awesome-kotlin"

    # Ruby
    # "https://github.com/sinatra/sinatra",

    # C++
    # "https://github.com/fmtlib/fmt",
]


def main():
    ingestion = IngestionPipeline()
    chunker = ChunkPipeline()

    success_repos = []
    failed_repos = []

    for repo_url in REPOS:
        name = repo_url.removesuffix(".git").split("/")[-1]
        print(f"\nProcessing: {repo_url}")

        try:
            files_metadata = ingestion.ingest(repo_url)
            all_chunks = chunker.chunk_repository(files_metadata, repo_name=name)

            print(f"Total files  : {len(files_metadata)}")
            print(f"Total chunks : {len(all_chunks)}")

            success_repos.append(repo_url)

        except Exception as e:
            print(f"Failed: {repo_url} — {e}")
            failed_repos.append(repo_url)

    print("\n" + "=" * 60)
    print(f"Success : {len(success_repos)}")
    print(f"Failed  : {len(failed_repos)}")


if __name__ == "__main__":
    main()
