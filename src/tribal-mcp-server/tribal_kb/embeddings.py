"""Generate optional, validated OpenAI embeddings without changing Markdown source."""

from __future__ import annotations

import math
import os

import httpx


# Validate a complete embedding response against its pinned vector space.
def validate_vectors(vectors, count: int, dimensions: int) -> list[list[float]]:
    if not isinstance(vectors, list) or len(vectors) != count:
        raise ValueError("Embedding response count does not match input")
    for vector in vectors:
        if not isinstance(vector, list) or len(vector) != dimensions:
            raise ValueError("Embedding dimensions do not match the configured model")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
               for v in vector):
            raise ValueError("Embedding values must be finite numbers")
    return vectors


class OpenAIEmbeddingClient:
    # Configure an optional provider and an injectable asynchronous HTTP client.
    def __init__(self, api_key=None, *, model="text-embedding-3-small", dimensions=1536,
                 base_url="https://api.openai.com/v1", http_client=None):
        self.api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY")
        self.model = model
        self.dimensions = dimensions
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client
        self.available = bool(self.api_key)

    # Request one ordered vector for every text and reject incompatible provider data.
    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.available:
            raise ValueError("OpenAI embeddings are unavailable without an API key")
        if not texts:
            return []
        payload = {"model": self.model, "input": texts, "dimensions": self.dimensions}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if self.http_client is None:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(self.base_url + "/embeddings", json=payload,
                                             headers=headers)
        else:
            response = await self.http_client.post(self.base_url + "/embeddings", json=payload,
                                                  headers=headers)
        response.raise_for_status()
        data = response.json()
        if data.get("model") != self.model:
            raise ValueError("Embedding response model does not match the configured model")
        entries = data.get("data")
        if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
            raise ValueError("Embedding response is missing data")
        if sorted(item.get("index", -1) for item in entries) != list(range(len(texts))):
            raise ValueError("Embedding response indices do not match input")
        return validate_vectors([item.get("embedding") for item in sorted(
            entries, key=lambda item: item["index"])], len(texts), self.dimensions)
