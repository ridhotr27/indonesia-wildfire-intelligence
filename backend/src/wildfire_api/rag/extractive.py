from __future__ import annotations

import re

from wildfire_api.llm.ollama import GeneratedAnswer, LocalModelError
from wildfire_api.rag.models import RetrievedPassage

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|[\r\n]+")
_QUESTION_TERMS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "can",
        "define",
        "describe",
        "does",
        "explain",
        "for",
        "how",
        "in",
        "is",
        "it",
        "mean",
        "of",
        "the",
        "to",
        "what",
        "which",
    }
)
_PAGE_CHROME = re.compile(
    r"\b(toggle submenu|publications access|centers distributed|all of the resources)\b",
    re.IGNORECASE,
)


def _terms(text: str) -> set[str]:
    return {
        token.casefold()
        for token in _TOKEN_PATTERN.findall(text)
        if len(token) > 1 and token.casefold() not in _QUESTION_TERMS
    }


class ExtractiveAnswerGenerator:
    """Produce a bounded answer made only from retrieved NASA evidence.

    This deterministic fallback is intentionally less fluent than the optional
    local LLM. It is useful for local development because it cannot introduce a
    claim or citation that was not present in the validated retrieved passages.
    """

    model_calls = 0

    async def __call__(
        self, question: str, passages: list[RetrievedPassage]
    ) -> GeneratedAnswer:
        question_terms = _terms(question)
        if not question_terms or not passages:
            raise LocalModelError("extractive answer requires a question and evidence")

        candidates: list[tuple[int, int, int, str, str]] = []
        for passage_rank, passage in enumerate(passages):
            for sentence_rank, raw_sentence in enumerate(_SENTENCE_BOUNDARY.split(passage.text)):
                sentence = re.sub(r"\s+", " ", raw_sentence).strip(" -")
                if not 35 <= len(sentence) <= 500 or _PAGE_CHROME.search(sentence):
                    continue
                overlap = question_terms.intersection(_terms(sentence))
                if not overlap:
                    continue
                # Prefer sentences covering more of the question while retaining
                # retrieval and source order as deterministic tie breakers.
                candidates.append(
                    (-len(overlap), passage_rank, sentence_rank, sentence, passage.chunk_id)
                )

        if not candidates:
            raise LocalModelError("retrieved passages do not contain answerable evidence")

        selected: list[tuple[int, int, str, str]] = []
        selected_text: set[str] = set()
        for _, passage_rank, sentence_rank, sentence, chunk_id in sorted(candidates):
            normalized = sentence.casefold()
            if normalized in selected_text:
                continue
            selected.append((passage_rank, sentence_rank, sentence, chunk_id))
            selected_text.add(normalized)
            if len(selected) == 3:
                break

        # Present sentences in evidence order rather than score order.
        selected.sort(key=lambda item: (item[0], item[1]))
        answer = " ".join(item[2] for item in selected)
        cited_chunk_ids = list(dict.fromkeys(item[3] for item in selected))
        if len(answer.split()) < 8 or not cited_chunk_ids:
            raise LocalModelError("retrieved evidence is insufficient for an extractive answer")
        return GeneratedAnswer(answer=answer, cited_chunk_ids=cited_chunk_ids)
