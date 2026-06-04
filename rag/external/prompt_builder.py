import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Dict
from datetime import datetime

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
- For code snippets, ALWAYS use fenced code blocks with triple backticks and specify the language.
- Do not wrap the entire response in a code block.
- Keep responses concise but complete.
- Add a phrase "RESPONSE END" at the end of your answer to indicate completion.
"""


class PromptBuilder:
    """Builds prompts for external (hosted) LLMs and includes file summaries.

    File summaries are loaded from data/summary/<repo_name>.json using the file
    path from each chunk. Summaries are then injected before the chunk content.
    """

    def __init__(self, debug: bool = True):
        self.debug = debug  # Enable/disable debug logging and file saving

    def build(self, query: str, context: ContextAssembly) -> PromptPayload:

        if context.chunks:
            print(f"DEBUG: First chunk repo = '{context.chunks[0].chunk.repo}'")
            print(f"DEBUG: All chunk repos: {set(c.chunk.repo for c in context.chunks)}")


        # Determine repository name from the chunks (assume all belong to same repo)
        repo_names = sorted({item.chunk.repo for item in context.chunks if item.chunk.repo})
        repo_hint = ", ".join(repo_names) if repo_names else "unknown"

        if self.debug:
            print("\n" + "=" * 80)
            print("📝 PROMPT BUILDER DEBUG")
            print("=" * 80)
            print(f"📦 Repository: {repo_hint}")
            print(f"📄 Total chunks retrieved: {len(context.chunks)}")
            print(f"📁 Unique files: {len(context.grouped_by_file)}")

        # Load summaries for the first repo (if multiple repos exist, handle accordingly)
        summaries: Dict[str, str] = {}
        if repo_names:
            summaries = self._load_summaries(repo_names[0])
            if self.debug:
                print(f"📚 Loaded {len(summaries)} file summaries from data/summary/{repo_names[0]}.json")
                if summaries:
                    sample_keys = list(summaries.keys())[:5]
                    print(f"   Sample keys: {sample_keys}")

        context_text = self._format_context(context, summaries)
        
        if self.debug:
            # Show first 500 chars of context to verify summaries are included
            print("\n📄 CONTEXT TEXT PREVIEW (first 500 chars):")
            print("-" * 40)
            print(context_text[:500])
            if len(context_text) > 500:
                print("... [truncated]")
            print("-" * 40)
            
            # Check specifically for summary markers
            if "**File summary:**" in context_text:
                summary_count = context_text.count("**File summary:**")
                print(f"✅ Found {summary_count} file summaries embedded in context")
            else:
                print("❌ WARNING: No '**File summary:**' found in context text!")
            
            # Save ONLY the latest request data to a single file (overwrites each time)
            self._save_latest_prompt(repo_hint, query, context_text)
        
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
            "stage=external_prompt_builder files=%d chunks=%d summaries_loaded=%d",
            len(context.grouped_by_file),
            len(context.chunks),
            len(summaries),
        )
        
        return PromptPayload(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            context_text=context_text,
            messages=messages,
        )

    @staticmethod
    @lru_cache(maxsize=8)
    def _load_summaries(repo_name: str) -> Dict[str, str]:
        """Load file summaries from data/summary/<repo_name>.json."""
        summary_path = Path(f"data/summary/{repo_name}.json")
        if not summary_path.exists():
            logger.warning("Summary file not found: %s", summary_path)
            print(f"❌ Summary file not found: {summary_path}")
            return {}

        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                summaries = json.load(f)
                if not isinstance(summaries, dict):
                    logger.warning("Summary file does not contain a dict: %s", summary_path)
                    return {}
                logger.info("Loaded %d summaries from %s", len(summaries), summary_path)
                print(f"✅ Loaded {len(summaries)} summaries from {summary_path}")
                return summaries
        except Exception as e:
            logger.error("Failed to load summaries from %s: %s", summary_path, e)
            print(f"❌ Error loading summaries: {e}")
            return {}

    def _normalize_path(self, path: str) -> str:
        """Normalize file path to match summary JSON keys."""
        # Remove leading './' or '/'
        if path.startswith('./'):
            path = path[2:]
        if path.startswith('/'):
            path = path[1:]
        # Replace backslashes with forward slashes
        path = path.replace('\\', '/')
        return path

    def _format_context(self, context: ContextAssembly, summaries: Dict[str, str]) -> str:
        """Format the context with file summaries injected above the chunk details."""
        lines: list[str] = []
        
        if self.debug:
            print("\n🔍 FORMATTING CONTEXT:")
            print("-" * 40)
        
        for file_path, items in context.grouped_by_file.items():
            if self.debug:
                print(f"\n📁 Raw chunk file_path: '{file_path}'")
                print(f"   - Number of chunks: {len(items)}")
            
            # Normalize the path for lookup
            normalized_path = self._normalize_path(file_path)
            if self.debug and normalized_path != file_path:
                print(f"   Normalized to: '{normalized_path}'")
            
            lines.append(f"## File: {file_path}")

            # Try to find summary using normalized path first, then original
            file_summary = summaries.get(normalized_path)
            if not file_summary and normalized_path != file_path:
                file_summary = summaries.get(file_path)
            
            if file_summary:
                if self.debug:
                    print(f"   ✅ Summary found (using key: '{normalized_path if normalized_path != file_path else file_path}')")
                lines.append(f"**File summary:** {file_summary}")
            else:
                if self.debug:
                    print(f"   ❌ No summary found for '{file_path}' (normalized: '{normalized_path}')")
                    if summaries:
                        # Show first few summary keys for comparison
                        sample_keys = list(summaries.keys())[:5]
                        print(f"   📋 Available summary keys (first 5): {sample_keys}")
                        # Check if any key ends with the same file name
                        base_name = Path(file_path).name
                        matching = [k for k in summaries.keys() if k.endswith(base_name) or base_name in k]
                        if matching:
                            print(f"   🔍 Possible match by filename: {matching[0]}")

            for item in items:
                chunk = item.chunk
                lines.append(
                    f"[{item.citation_id}] symbol={chunk.symbol or '-'} "
                    f"lang={chunk.language} lines={chunk.start_line}-{chunk.end_line}"
                )
                lines.append(chunk.content)
                lines.append("")
        
        if self.debug:
            print("\n" + "=" * 80)
        
        return "\n".join(lines).strip()
    
    def _save_latest_prompt(self, repo_name: str, query: str, context_text: str) -> None:
        """
        Save the full prompt context to a single file (overwrites each time).
        Only called when debug=True.
        """
        try:
            # Fixed file path - always overwrites
            prompt_file = Path("data/debug_latest_prompt.txt")
            prompt_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(prompt_file, "w", encoding="utf-8") as f:
                f.write(f"Repository: {repo_name}\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"Query: {query}\n")
                f.write("=" * 80 + "\n")
                f.write("FULL CONTEXT TEXT (with summaries if available):\n")
                f.write("=" * 80 + "\n")
                f.write(context_text)
                f.write("\n" + "=" * 80 + "\n")
                f.write("SYSTEM PROMPT (first 500 chars):\n")
                f.write("=" * 80 + "\n")
                f.write(SYSTEM_PROMPT[:500])
                if len(SYSTEM_PROMPT) > 500:
                    f.write("... [truncated, see code for full]")
            
            print(f"\n💾 Latest prompt saved to: {prompt_file}")
        except Exception as e:
            logger.error(f"Failed to save latest prompt: {e}")