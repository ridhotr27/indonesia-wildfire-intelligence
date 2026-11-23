from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

from langchain_core.embeddings import Embeddings

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class HashingEmbeddings(Embeddings):
    """Deterministic local embeddings for tests and offline development.

    This feature-hashing implementation has no model download or API cost. It is
    deliberately not presented as the production embedding choice; Q01 must
    measure the approved production retriever.
    """

    def __init__(self, dimensions: int = 512, idf: dict[str, float] | None = None) -> None:
        if not 64 <= dimensions <= 4096:
            raise ValueError("dimensions must be between 64 and 4096")
        self.dimensions = dimensions
        self.idf = idf or {}

    @staticmethod
    def _terms(text: str) -> list[str]:
        tokens = TOKEN_PATTERN.findall(text.casefold())
        return tokens + [f"{left}_{right}" for left, right in zip(tokens, tokens[1:], strict=False)]

    @classmethod
    def from_texts(cls, texts: list[str], dimensions: int = 512) -> HashingEmbeddings:
        document_frequency: Counter[str] = Counter()
        for text in texts:
            document_frequency.update(set(cls._terms(text)))
        total = len(texts)
        idf = {
            term: math.log((1 + total) / (1 + frequency)) + 1
            for term, frequency in document_frequency.items()
        }
        return cls(dimensions=dimensions, idf=idf)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        term_counts = Counter(self._terms(text))
        for term, count in term_counts.items():
            digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign * count * self.idf.get(term, 1.0)
        magnitude = math.sqrt(sum(value * value for value in vector))
        return [value / magnitude for value in vector] if magnitude else vector

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)
