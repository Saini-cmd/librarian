from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import streamlit as st


st.set_page_config(page_title="Code RAG", page_icon="📚", layout="wide")

COLLECTION_NAME = "code_chunks"


st.markdown(
    """
    <style>
    .block-container { padding-top: 1.1rem; padding-bottom: 1.1rem; }
    .hero {
        padding: 1.2rem 1.4rem;
        border-radius: 1rem;
        background: linear-gradient(135deg, rgba(24,31,48,0.98), rgba(36,46,72,0.96));
        color: white;
        border: 1px solid rgba(255,255,255,0.08);
        margin-bottom: 1rem;
    }
    .hero h1 { margin: 0; font-size: 2rem; }
    .hero p { margin: 0.35rem 0 0 0; color: rgba(255,255,255,0.75); }
    .mini-card {
        padding: 0.8rem 0.95rem;
        border-radius: 0.9rem;
        background: rgba(250,250,252,0.94);
        border: 1px solid rgba(15,23,42,0.08);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_qdrant_client():
    from vector_store.qdrant_client import QdrantManager

    return QdrantManager().get_client()


@st.cache_resource
def get_ingestion_pipeline():
    from ingestion.ingestion_pipeline import IngestionPipeline

    return IngestionPipeline()


@st.cache_resource
def get_chunk_pipeline():
    from chunking.chunk_pipeline import ChunkPipeline

    return ChunkPipeline()


@st.cache_resource
def get_embedding_pipeline():
    from embedding.embedding_pipeline import EmbeddingPipeline

    return EmbeddingPipeline()


@st.cache_resource
def get_retrieval_pipeline():
    from retrieval.retrieval_pipeline import RetrievalPipeline

    return RetrievalPipeline()


@st.cache_resource
def get_answer_generator():
    from rag.answer_generator import AnswerGenerator

    return AnswerGenerator()


def collection_exists(client, collection_name: str) -> bool:
    return any(collection.name == collection_name for collection in client.get_collections().collections)


def repo_name_from_url(repo_url: str) -> str:
    parsed = urlparse(repo_url.strip())
    name = Path(parsed.path).name
    if name.endswith(".git"):
        name = name[:-4]
    return name or "repo"


def chunk_file_path(repo_name: str) -> Path:
    return Path("data/chunks") / f"{repo_name}.pkl"


def has_ready_embeddings() -> bool:
    client = get_qdrant_client()
    return collection_exists(client, COLLECTION_NAME)


st.markdown(
    """
    <div class="hero">
        <h1>Code RAG</h1>
        <p>Paste a repository link, run the pipeline, then chat with the embedded codebase.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

left, right = st.columns([1.05, 0.95], gap="large")

with left:
    st.subheader("Start Pipeline")
    repo_url = st.text_input("Repository link", value="https://github.com/psf/requests", placeholder="https://github.com/owner/repo")

    repo_name = repo_name_from_url(repo_url)
    st.markdown(
        f"<div class='mini-card'>Auto-detected repo name: <b>{repo_name}</b></div>",
        unsafe_allow_html=True,
    )

    run_pipeline = st.button("Run ingest → chunk → embed", type="primary", use_container_width=True)

    progress_area = st.container(border=True)

    if run_pipeline:
        if not repo_url.strip():
            st.warning("Paste a repository link first.")
        else:
            progress_bar = st.progress(0)
            stage_text = progress_area.empty()
            detail_text = progress_area.empty()

            try:
                stage_text.info("Stage 1: Ingesting repository")
                detail_text.write("Cloning and scanning files...")
                progress_bar.progress(10)

                files = get_ingestion_pipeline().ingest(repo_url.strip())
                detail_text.success(f"Ingested {len(files)} files")
                progress_bar.progress(35)

                stage_text.info("Stage 2: Chunking repository")
                detail_text.write("Creating code chunks...")
                chunks = get_chunk_pipeline().chunk_repository(files, repo_name=repo_name)
                detail_text.success(f"Created {len(chunks)} chunks")
                progress_bar.progress(65)

                stage_text.info("Stage 3: Embedding chunks")
                detail_text.write("Indexing chunks into Qdrant...")
                get_embedding_pipeline().embed_repo(repo_name)
                detail_text.success("Embedding complete")
                progress_bar.progress(100)

                stage_text.success("Pipeline complete")
                st.session_state["ready_for_chat"] = True
                st.session_state["pipeline_repo_name"] = repo_name
                st.success("Repository is ready for chat.")
                st.rerun()

            except Exception as exc:
                progress_bar.progress(0)
                stage_text.error("Pipeline failed")
                detail_text.exception(exc)

    st.markdown("### Current status")
    status_cols = st.columns(2)
    with status_cols[0]:
        st.markdown(
            f"<div class='mini-card'>Qdrant collection: <b>{'ready' if has_ready_embeddings() else 'not ready'}</b></div>",
            unsafe_allow_html=True,
        )
    with status_cols[1]:
        local_chunks = chunk_file_path(repo_name)
        st.markdown(
            f"<div class='mini-card'>Chunk file: <b>{'present' if local_chunks.exists() else 'missing'}</b></div>",
            unsafe_allow_html=True,
        )

with right:
    st.subheader("Chat")

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [
            {"role": "assistant", "content": "Run the pipeline first, then ask a question here."}
        ]

    ready_for_chat = st.session_state.get("ready_for_chat", False) or has_ready_embeddings()

    if not ready_for_chat:
        st.info("Chat will be enabled after the repository has been ingested, chunked, and embedded.")

    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    question = st.chat_input("Ask a question about the repository", disabled=not ready_for_chat)

    if question:
        st.session_state.chat_messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.write(question)

        if not has_ready_embeddings():
            answer = "No embeddings found yet. Run the pipeline first."
            st.session_state.chat_messages.append({"role": "assistant", "content": answer})
            with st.chat_message("assistant"):
                st.write(answer)
        else:
            status_box = st.status("Generating answer...", expanded=True)
            try:
                status_box.write("1. Loading retrieval pipeline")
                retrieval = get_retrieval_pipeline()
                status_box.write("2. Running hybrid retrieval and reranking")
                answerer = get_answer_generator()

                retrieved = retrieval.retrieve(question)
                status_box.write(f"Retrieved {len(retrieved)} chunks")

                prompt_context = answerer.context_builder.build(retrieved)
                prompt_payload = answerer.prompt_builder.build(query=question, context=prompt_context)

                status_box.write("3. Streaming response from Gemma")
                streamed_answer = ""
                with st.chat_message("assistant"):
                    answer_placeholder = st.empty()
                    for token in answerer.llm_client.stream_generate(prompt_payload.messages):
                        streamed_answer += token
                        answer_placeholder.write(streamed_answer + "▌")

                    citations = answerer._map_citations(streamed_answer, prompt_context)
                    final_answer = answerer._append_citation_fallback(streamed_answer, citations)
                    answer_placeholder.write(final_answer)

                st.session_state.chat_messages.append({"role": "assistant", "content": final_answer})

                with st.expander("Citations"):
                    for citation in citations:
                        st.write(
                            f"[{citation.citation_id}] {citation.file_path}:{citation.start_line}-{citation.end_line} "
                            f"{citation.language}"
                        )

                status_box.update(label="Answer ready", state="complete")

            except Exception as exc:
                status_box.update(label="Generation failed", state="error")
                st.session_state.chat_messages.append({"role": "assistant", "content": f"Error: {exc}"})
                st.exception(exc)
