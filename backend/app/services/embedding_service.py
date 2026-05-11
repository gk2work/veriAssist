"""
VeriAssist v2.0 — Embedding Service

Wraps Ollama's nomic-embed-text model for generating embeddings locally.
Used by RAG service to embed both documents (during ingestion) and
queries (during retrieval).

Embedding model: nomic-embed-text (137M params, ~0.5 GB RAM)
Dimensions: 768
"""

import httpx
import logging
from typing import Optional

logger = logging.getLogger("veriassist.embedding")

OLLAMA_BASE = __import__("os").environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_EMBED_MODEL = "nomic-embed-text"


class EmbeddingService:
    def __init__(self, base_url: str = OLLAMA_BASE, model: str = DEFAULT_EMBED_MODEL):
        self.base_url = base_url
        self.model = model
        self._client: Optional[httpx.AsyncClient] = None
        self._dimension: Optional[int] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=10.0),
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def embed_text(self, text: str) -> list[float]:
        """Embed a single text string. Returns a 768-dim float vector."""
        client = await self._get_client()
        try:
            resp = await client.post(
                "/api/embeddings",
                json={"model": self.model, "prompt": text},
            )
            resp.raise_for_status()
            data = resp.json()
            embedding = data.get("embedding", [])

            if not embedding:
                logger.error(f"Empty embedding returned for text: {text[:80]}...")
                return []

            # Cache dimension on first call
            if self._dimension is None:
                self._dimension = len(embedding)
                logger.info(f"Embedding dimension: {self._dimension}")

            return embedding

        except httpx.ConnectError:
            logger.error("Cannot connect to Ollama for embeddings. Is it running?")
            raise ConnectionError(
                f"Ollama not reachable at {self.base_url}. "
                f"Make sure Ollama is running and {self.model} is pulled."
            )
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            raise

    async def embed_batch(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """
        Embed multiple texts. Processes sequentially since Ollama
        handles one embedding at a time.

        For 8GB RAM MacBook: batch_size doesn't matter much since
        nomic-embed-text is tiny (~0.5 GB). The bottleneck is
        sequential API calls, not memory.
        """
        embeddings = []
        total = len(texts)

        for i, text in enumerate(texts):
            if i % 50 == 0 and i > 0:
                logger.info(f"Embedding progress: {i}/{total}")

            emb = await self.embed_text(text)
            embeddings.append(emb)

        logger.info(f"Embedded {total} texts successfully")
        return embeddings

    async def health(self) -> dict:
        """Check if embedding model is available."""
        try:
            # Try a test embedding
            test = await self.embed_text("test")
            return {
                "status": "available",
                "model": self.model,
                "dimension": len(test),
            }
        except Exception as e:
            return {
                "status": "unavailable",
                "model": self.model,
                "error": str(e),
            }

    @property
    def dimension(self) -> int:
        """Return cached embedding dimension (768 for nomic-embed-text)."""
        return self._dimension or 768


# ── Sync wrapper for use in ingestion scripts ──────────────

class EmbeddingServiceSync:
    """
    Synchronous wrapper for use in CLI scripts (ingest_docs.py).
    Uses httpx sync client instead of async.
    """

    def __init__(self, base_url: str = OLLAMA_BASE, model: str = DEFAULT_EMBED_MODEL):
        self.base_url = base_url
        self.model = model
        self._client = httpx.Client(
            base_url=base_url,
            timeout=httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=10.0),
        )

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text string synchronously."""
        resp = self._client.post(
            "/api/embeddings",
            json={"model": self.model, "prompt": text},
        )
        resp.raise_for_status()
        return resp.json().get("embedding", [])

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts synchronously with progress logging."""
        embeddings = []
        total = len(texts)
        for i, text in enumerate(texts):
            if i % 50 == 0 and i > 0:
                logger.info(f"Embedding progress: {i}/{total}")
            embeddings.append(self.embed_text(text))
        logger.info(f"Embedded {total} texts successfully")
        return embeddings

    def close(self):
        self._client.close()


# Singleton async instance (used by FastAPI backend)
embedding_service = EmbeddingService()