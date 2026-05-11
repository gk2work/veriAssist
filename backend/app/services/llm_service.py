"""
VeriAssist v2.0 — Ollama LLM Service

Wraps the Ollama REST API for chat, generation, model listing, and health checks.
Supports streaming via async generators for SSE.
"""

import httpx
import json
import logging
from typing import AsyncGenerator, Optional

logger = logging.getLogger("veriassist.llm")

# Default models ranked by quality (first available is used)
DEFAULT_MODELS = [
    "qwen2.5-coder:7b-instruct-q4_K_M",
    "qwen2.5-coder:3b-instruct",
    "codellama:7b-instruct-q4_K_M",
    "llama3.1:8b-instruct-q4_K_M",
]

OLLAMA_BASE = __import__("os").environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


class OllamaService:
    def __init__(self, base_url: str = OLLAMA_BASE):
        self.base_url = base_url
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(connect=5.0, read=300.0, write=10.0, pool=10.0),
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── Health & Model Management ──────────────────────────

    async def health(self) -> dict:
        """Check if Ollama is running and list available models."""
        try:
            client = await self._get_client()
            resp = await client.get("/api/tags")
            resp.raise_for_status()
            data = resp.json()
            models = [m["name"] for m in data.get("models", [])]
            default = self._pick_default_model(models)
            return {
                "ollama": "connected",
                "models": models,
                "default_model": default,
            }
        except (httpx.ConnectError, httpx.ConnectTimeout):
            return {
                "ollama": "disconnected",
                "models": [],
                "default_model": "",
            }
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return {
                "ollama": f"error: {str(e)}",
                "models": [],
                "default_model": "",
            }

    def _pick_default_model(self, available: list[str]) -> str:
        """Pick the best available model from our preference list."""
        for preferred in DEFAULT_MODELS:
            for avail in available:
                # Match by prefix (ollama may add :latest etc)
                if avail.startswith(preferred.split(":")[0]):
                    return avail
        return available[0] if available else ""

    async def list_models(self) -> list[dict]:
        """List all models available in Ollama with details."""
        try:
            client = await self._get_client()
            resp = await client.get("/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return data.get("models", [])
        except Exception as e:
            logger.error(f"Failed to list models: {e}")
            return []

    # ── Chat (Streaming) ──────────────────────────────────

    async def chat_stream(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """
        Stream chat completion tokens from Ollama.
        Yields individual token strings as they arrive.
        """
        if not model:
            status = await self.health()
            model = status["default_model"]
            if not model:
                yield "[ERROR] No models available. Run: ollama pull qwen2.5-coder:3b-instruct"
                return

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "top_p": 0.9,
            },
        }

        try:
            client = await self._get_client()
            async with client.stream("POST", "/api/chat", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            yield token
                        if chunk.get("done", False):
                            return
                    except json.JSONDecodeError:
                        continue
        except httpx.ConnectError:
            yield "[ERROR] Cannot connect to Ollama. Start it with: ollama serve"
        except httpx.ReadTimeout:
            yield "\n\n[TIMEOUT] Response took too long. Try a shorter prompt or smaller model."
        except Exception as e:
            logger.error(f"Chat stream error: {e}")
            yield f"[ERROR] {str(e)}"

    # ── Chat (Non-Streaming) ──────────────────────────────

    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """Non-streaming chat. Returns complete response as string."""
        tokens = []
        async for token in self.chat_stream(messages, model, temperature, max_tokens):
            tokens.append(token)
        return "".join(tokens)


# Singleton instance
ollama_service = OllamaService()
