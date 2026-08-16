"""
DeepSeek-based LLM judges for the generation metrics.

Faithfulness and Answer Relevance are scored 0-1 by the judge. Prompts are pure
functions (testable without an LLM); the ``Judge`` class wraps ``LLMClient`` and
falls back to ``None`` per metric when a call fails so one bad call never sinks a
whole run.
"""

import logging
import re

from prompts import (
    JUDGE_ANSWER_RELEVANCE_SYSTEM_PROMPT,
    JUDGE_FAITHFULNESS_SYSTEM_PROMPT,
    judge_answer_relevance_user_prompt,
    judge_faithfulness_user_prompt,
)
from rag.llm_client import LLMClient


logger = logging.getLogger(__name__)

_NUMBER_RE = re.compile(r"-?\d(?:\.\d+)?|\.\d+")


def faithfulness_prompt(
    question: str, answer: str, contexts: list[str]
) -> list[dict[str, str]]:
    """Build judge messages: is the answer supported by the retrieved context?"""
    return [
        {"role": "system", "content": JUDGE_FAITHFULNESS_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": judge_faithfulness_user_prompt(question, answer, contexts),
        },
    ]


def answer_relevance_prompt(question: str, answer: str) -> list[dict[str, str]]:
    """Build judge messages: does the answer address the question?"""
    return [
        {"role": "system", "content": JUDGE_ANSWER_RELEVANCE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": judge_answer_relevance_user_prompt(question, answer),
        },
    ]


def parse_score(text: str) -> float | None:
    """Extract a 0-1 score from judge output; None if none is present."""
    if not text:
        return None
    match = _NUMBER_RE.search(text)
    if not match:
        return None
    try:
        value = float(match.group(0))
    except ValueError:
        return None
    return max(0.0, min(1.0, value))


class Judge:
    """DeepSeek judge wrapper; each metric returns None on failure."""

    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or LLMClient()

    def faithfulness(self, question: str, answer: str, contexts: list[str]) -> float | None:
        return self._score(faithfulness_prompt(question, answer, contexts))

    def answer_relevance(self, question: str, answer: str) -> float | None:
        return self._score(answer_relevance_prompt(question, answer))

    def _score(self, messages: list[dict[str, str]]) -> float | None:
        try:
            response = self.llm.generate(messages)
            return parse_score(response.text)
        except Exception:
            logger.exception("judge_call_failed")
            return None

    def sanity_check(self) -> dict[str, dict[str, float | bool]]:
        """Verify the judge discriminates between a grounded and an ungrounded answer.

        A judge that scores a hallucinated, off-topic answer as highly as a good
        one cannot be trusted to measure the generation metrics. Returns per
        metric the good/bad scores and whether they differ by at least 0.3.
        """
        question = "How does the login function authenticate a user?"
        context = [
            "def login(user, password):\n"
            "    token = verify(user, password)\n"
            "    return token"
        ]
        good = (
            "The login function calls verify(user, password) to check the "
            "credentials and returns the resulting token."
        )
        bad = (
            "The login function launches a rocket to Mars and then orders tea."
        )

        results: dict[str, dict[str, float | bool]] = {}
        pairs = {
            "faithfulness": (
                self.faithfulness(question, good, context),
                self.faithfulness(question, bad, context),
            ),
            "answer_relevance": (
                self.answer_relevance(question, good),
                self.answer_relevance(question, bad),
            ),
        }
        for name, (good_score, bad_score) in pairs.items():
            if good_score is None or bad_score is None:
                results[name] = {"good": good_score, "bad": bad_score, "pass": False}
                continue
            passes = (good_score - bad_score) >= 0.3
            results[name] = {"good": good_score, "bad": bad_score, "pass": passes}
        return results
