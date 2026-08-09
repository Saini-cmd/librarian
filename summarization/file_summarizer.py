import tiktoken

from rag.llm_client import LLMClient
from summarization.llm_config import build_summarizer_config


_ENCODING = "cl100k_base"
_MAX_FILE_TOKENS = 3000


_SUMMARIZATION_SYSTEM_PROMPT = (
    "You are a code analyst. Summarize the given code file in 100 words or fewer. "
    "Describe its purpose, main exports/classes/functions, and its role in the codebase. "
    "Be concise and technical."
)


class FileSummarizer:

    def __init__(self):
        self._client = LLMClient(build_summarizer_config())
        self._tokenizer = tiktoken.get_encoding(_ENCODING)

    def summarize_file(self, file_path: str, language: str) -> str:
        content = self._read_and_truncate(file_path)
        if not content:
            return ""

        messages = [
            {"role": "system", "content": _SUMMARIZATION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Language: {language}\n"
                    f"File: {file_path}\n\n"
                    f"```{language}\n{content}\n```"
                ),
            },
        ]

        response = self._client.generate(messages, stream=False)
        return response.text.strip()

    def _read_and_truncate(self, file_path: str) -> str:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except Exception:
            return ""

        tokens = self._tokenizer.encode(text)
        if len(tokens) <= _MAX_FILE_TOKENS:
            return text
        return self._tokenizer.decode(tokens[:_MAX_FILE_TOKENS])
