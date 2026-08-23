"""
Single source of truth for every LLM prompt template in the project.

All system prompts and user-prompt templates live here so they can be audited,
versioned, and tuned in one place. Consumers keep their assembly logic (message
list construction, retry loops, context grouping) but reference the shared
templates below.

Consumers:
- ``rag/prompt_builder.py`` — RAG answer generation
- ``summarization/file_summarizer.py`` — per-file summaries
- ``memory/worker.py`` — chat-memory rolling summaries
- ``backend/routers/repositories.py`` — graph-panel node explanation
- ``evaluation/llm_judge.py`` — Faithfulness / Answer Relevance judges
- ``evaluation/golden_set.py`` — golden-set query paraphrase
"""

# --------------------------------------------------------------------------- #
# RAG answer generation (rag/prompt_builder.py)
# --------------------------------------------------------------------------- #

RAG_SYSTEM_PROMPT = """You are a senior software engineer helping a developer understand a codebase.
Answer the question directly and naturally, the way an experienced engineer would explain code to a teammate.
Ground your answer in the retrieved context, citing the chunks you actually use as [C1], [C2], etc.
Do not narrate the retrieval process, describe the context, or dwell on what the context does not contain.
If the retrieved code does not answer the question, say so in one short sentence rather than speculating.
Never invent APIs, files, or behavior that are not in the context.
Keep it concise and technical."""

RAG_MEMORY_GUIDANCE = (
    "The conversation history and long-term memory below provide context about previous "
    "questions and answers. They are not citable and may reference an earlier version of "
    "the code — when they conflict with the retrieved context, trust the retrieved context."
)

# Context formatting templates (used by PromptBuilder._format_context).
RAG_CONTEXT_FILE_HEADER = "## File: {file_path}"
RAG_CONTEXT_SUMMARY = "Summary: {summary}"
RAG_CONTEXT_CHUNK_HEADER = (
    "[{citation_id}] symbol={symbol} lang={language} lines={start_line}-{end_line}"
)

# User prompt framing (used by PromptBuilder._build_user_prompt).
RAG_USER_REPOSITORY_SCOPE = "Repository scope: {repo_hint}"
RAG_USER_LONG_TERM_MEMORY = "Long-term memory:\n{memory}"
RAG_USER_RETRIEVED_CONTEXT = "Retrieved context:\n{context}"
RAG_USER_QUERY = "User query:\n{query}"


def rag_user_prompt(
    repo_hint: str,
    context_text: str,
    memory_texts: list[str],
    query: str,
) -> str:
    """Assemble the RAG user message from repository scope, memory, context, query."""
    parts = [RAG_USER_REPOSITORY_SCOPE.format(repo_hint=repo_hint)]
    if memory_texts:
        parts.append(
            RAG_USER_LONG_TERM_MEMORY.format(memory="\n\n".join(memory_texts))
        )
    parts.append(RAG_USER_RETRIEVED_CONTEXT.format(context=context_text))
    parts.append(RAG_USER_QUERY.format(query=query))
    return "\n\n".join(parts)


# --------------------------------------------------------------------------- #
# Per-file summarization (summarization/file_summarizer.py)
# --------------------------------------------------------------------------- #

FILE_SUMMARIZATION_SYSTEM_PROMPT = (
    "You are a code analyst. Summarize the given code file in 100 words or fewer. "
    "Describe its purpose, main exports/classes/functions, and its role in the codebase. "
    "Be concise and technical."
)


def file_summarization_user_prompt(language: str, file_path: str, content: str) -> str:
    """Assemble the file-summarization user message."""
    return (
        f"Language: {language}\n"
        f"File: {file_path}\n\n"
        f"```{language}\n{content}\n```"
    )


# --------------------------------------------------------------------------- #
# Chat-memory rolling summaries (memory/worker.py)
# --------------------------------------------------------------------------- #

MEMORY_ROLLUP_MERGE_SYSTEM_PROMPT = (
    "You are a conversation summarizer for a code-assistant chat. "
    "Merge the EXISTING SUMMARY with the NEW MESSAGES into one concise "
    "rolling summary (under 150 words). Keep it factual and concrete; "
    "preserve key technical decisions and unresolved points."
)

MEMORY_ROLLUP_FRESH_SYSTEM_PROMPT = (
    "You are a conversation summarizer for a code-assistant chat. "
    "Summarize the conversation in under 150 words. Keep it factual and "
    "concrete; preserve key technical decisions and unresolved points."
)

MEMORY_ROLLUP_EXISTING_SUMMARY = "EXISTING SUMMARY:\n{summary}"
MEMORY_ROLLUP_NEW_MESSAGES = "NEW MESSAGES:\n{messages}"


def memory_rollup_user_prompt(
    existing_summary: str | None, messages_text: str
) -> str:
    """Assemble the rollup user message (existing-summary variant or fresh)."""
    if existing_summary:
        return (
            MEMORY_ROLLUP_EXISTING_SUMMARY.format(summary=existing_summary)
            + "\n\n"
            + MEMORY_ROLLUP_NEW_MESSAGES.format(messages=messages_text)
        )
    return messages_text


# --------------------------------------------------------------------------- #
# Graph-panel node explanation (backend/routers/repositories.py)
# --------------------------------------------------------------------------- #

EXPLAIN_SYSTEM_PROMPT = (
    "You are a senior software engineer explaining a single code node. "
    "Explain concisely in markdown what the code does and how it works, "
    "including its inputs and outputs. Stay grounded in the provided code — "
    "do not invent behavior, APIs, or files that are not present. "
    "Keep the explanation under 150 words."
)

EXPLAIN_USER_CODE_NODE = "Code node: {label} ({kind})"
EXPLAIN_USER_FILE = "File: {file_path}{loc}"


def explain_user_prompt(
    label: str,
    kind: str,
    file_path: str,
    loc: str,
    code: str,
) -> str:
    """Assemble the node-explanation user message."""
    return (
        f"{EXPLAIN_USER_CODE_NODE.format(label=label, kind=kind)}\n"
        f"{EXPLAIN_USER_FILE.format(file_path=file_path, loc=loc)}\n\n"
        f"```\n{code}\n```\n\n"
        "Explain this code."
    )


# --------------------------------------------------------------------------- #
# Eval judges (evaluation/llm_judge.py)
# --------------------------------------------------------------------------- #

JUDGE_FAITHFULNESS_SYSTEM_PROMPT = (
    "You are an expert judge for a code retrieval-augmented generation (RAG) "
    "system. Assess whether the ANSWER is supported by the RETRIEVED CONTEXT. "
    "Treat every claim in the answer as unsupported unless it can be directly "
    "verified in the context. A claim that contradicts the context, adds facts "
    "not present in it, or references code the context does not contain is "
    "unsupported. Score = the fraction of the answer's claims that are "
    "supported. Be strict: do NOT award credit for unverifiable claims. "
    "Output ONLY a number between 0 and 1 (for example 0.85). No explanation, "
    "no code."
)

JUDGE_ANSWER_RELEVANCE_SYSTEM_PROMPT = (
    "You are an expert judge for a code retrieval-augmented generation (RAG) "
    "system. Evaluate how well the ANSWER addresses the QUESTION. "
    "Step 1: enumerate the distinct things the question asks for (its "
    "requirements). Step 2: for each requirement, mark whether the answer "
    "addresses it directly and on-topic. Ignore factual correctness and source "
    "grounding. Output ONLY the fraction of requirements the answer addresses, "
    "as a number between 0 and 1 (for example 0.7). No explanation, no code."
)

JUDGE_QUESTION = "QUESTION:\n{question}"
JUDGE_ANSWER = "ANSWER:\n{answer}"
JUDGE_RETRIEVED_CONTEXT = "RETRIEVED CONTEXT:\n{context}"


def judge_faithfulness_user_prompt(
    question: str, answer: str, contexts: list[str]
) -> str:
    """Assemble the faithfulness-judge user message."""
    return (
        f"{JUDGE_QUESTION.format(question=question)}\n\n"
        f"{JUDGE_ANSWER.format(answer=answer)}\n\n"
        f"{JUDGE_RETRIEVED_CONTEXT.format(context='\n---\n'.join(contexts))}"
    )


def judge_answer_relevance_user_prompt(question: str, answer: str) -> str:
    """Assemble the answer-relevance-judge user message."""
    return (
        f"{JUDGE_QUESTION.format(question=question)}\n\n"
        f"{JUDGE_ANSWER.format(answer=answer)}"
    )


# --------------------------------------------------------------------------- #
# Golden-set query paraphrase (evaluation/golden_set.py)
# --------------------------------------------------------------------------- #

GOLDEN_PARAPHRASE_SYSTEM_PROMPT = (
    "You are building an evaluation dataset for a code-search and code-QA "
    "system. Given a code snippet, write exactly one natural-language question "
    "that a developer working in this repository would ask, and that this code "
    "answers. Do NOT mention the symbol, function, or class name directly. "
    "Output only the question, no preamble."
)

GOLDEN_PARAPHRASE_FORCE_HIDE_SYSTEM_PROMPT = (
    GOLDEN_PARAPHRASE_SYSTEM_PROMPT
    + " CRITICAL: the previous question accidentally revealed the symbol name. "
    "Rewrite it so the symbol, function, or class name NEVER appears, while "
    "still describing what the code does."
)

GOLDEN_PARAPHRASE_LANGUAGE = "Language: {language}"
GOLDEN_PARAPHRASE_FILE = "File: {file_path}"
GOLDEN_PARAPHRASE_LINES = "Lines: {start_line}-{end_line}"


def golden_paraphrase_user_prompt(
    language: str,
    file_path: str,
    start_line: int,
    end_line: int,
    content: str,
) -> str:
    """Assemble the paraphrase user message for a sampled code entity."""
    return (
        f"{GOLDEN_PARAPHRASE_LANGUAGE.format(language=language)}\n"
        f"{GOLDEN_PARAPHRASE_FILE.format(file_path=file_path)}\n"
        f"{GOLDEN_PARAPHRASE_LINES.format(start_line=start_line, end_line=end_line)}\n\n"
        f"```\n{content}\n```"
    )
