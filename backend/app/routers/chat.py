"""
VeriAssist v2.0 — Chat Router

POST /api/chat         — Streaming chat with RAG-augmented context
GET  /api/docs/search  — Direct document search (Phase 2)
GET  /api/models       — List available Ollama models
GET  /api/health       — System health check (Ollama + RAG + formal tools)
"""

import json
import shutil
import logging
from typing import Optional
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from app.models.schemas import ChatRequest
from app.services.llm_service import ollama_service
from app.services.prompt_templates import get_system_prompt
from app.services.rag_service import (
    rag_service,
    should_use_rag,
    get_rag_collections_for_mode,
)

logger = logging.getLogger("veriassist.chat")
router = APIRouter(prefix="/api", tags=["chat"])


# ═══════════════════════════════════════════════════════════════
# POST /api/chat — Streaming chat with optional RAG
# ═══════════════════════════════════════════════════════════════

@router.post("/chat")
async def chat(req: ChatRequest):
    """
    Streaming chat endpoint with RAG-augmented context.

    RAG behavior per mode:
    - chat / debug: always retrieves relevant docs
    - generate / sva / formal: retrieves only for informational queries
      (contains "?", "what is", "how to", etc.), skips for pure generation

    Returns Server-Sent Events (SSE):
      data: {"token": "...", "done": false, "sources": null}
      ...
      data: {"token": "", "done": true, "sources": [...]}
    """
    mode = req.mode.value
    system_prompt = get_system_prompt(mode)
    sources = []

    # ── Decide: RAG or direct ──────────────────────────────
    use_rag = should_use_rag(mode, req.message)

    if use_rag:
        # Get mode-specific collection filter
        collections = get_rag_collections_for_mode(mode)

        # Build RAG-augmented messages
        try:
            messages = await rag_service.build_augmented_messages(
                query=req.message,
                system_prompt=system_prompt,
                history=req.history,
                top_k=5,
                collections=collections,
            )

            # Collect sources for citation
            retrieved = await rag_service.retrieve(
                query=req.message,
                top_k=5,
                collections=collections,
            )
            sources = [
                {
                    "source": r["source"],
                    "section": r["section"],
                    "score": r["score"],
                    "collection": r["collection"],
                }
                for r in retrieved
            ]

            logger.info(
                f"RAG active for mode={mode}: {len(sources)} sources retrieved "
                f"(best: {sources[0]['source']} score={sources[0]['score']:.3f})"
                if sources else f"RAG active for mode={mode}: no sources found"
            )

        except Exception as e:
            logger.warning(f"RAG failed, falling back to direct: {e}")
            messages = _build_direct_messages(system_prompt, req)
    else:
        messages = _build_direct_messages(system_prompt, req)
        logger.info(f"RAG skipped for mode={mode} (pure generation request)")

    # ── Stream response ────────────────────────────────────

    async def event_stream():
        async for token in ollama_service.chat_stream(
            messages=messages,
            model=req.model,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        ):
            data = json.dumps({"token": token, "done": False, "sources": None})
            yield f"data: {data}\n\n"

        # Final event includes sources for the frontend to display
        data = json.dumps({"token": "", "done": True, "sources": sources})
        yield f"data: {data}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _build_direct_messages(system_prompt: str, req: ChatRequest) -> list[dict]:
    """Build message list without RAG (Phase 1 behavior)."""
    messages = [{"role": "system", "content": system_prompt}]
    for msg in req.history[-10:]:
        messages.append({
            "role": msg.get("role", "user"),
            "content": msg.get("content", ""),
        })
    messages.append({"role": "user", "content": req.message})
    return messages


# ═══════════════════════════════════════════════════════════════
# GET /api/docs/search — Direct document search
# ═══════════════════════════════════════════════════════════════

@router.get("/docs/search")
async def search_docs(
    q: str = Query(..., description="Search query"),
    top_k: int = Query(default=10, ge=1, le=50, description="Number of results"),
    collection: Optional[str] = Query(default=None, description="Filter by collection name"),
):
    """
    Search the knowledge base directly. Returns matching chunks
    with scores, sources, and metadata.

    Example: GET /api/docs/search?q=uvm_config_db&top_k=5
    """
    try:
        results = await rag_service.search(
            query=q,
            top_k=top_k,
            collection=collection,
        )
        return {
            "query": q,
            "count": len(results),
            "results": [
                {
                    "text": r["text"][:500],  # Truncate for API response
                    "full_text": r["text"],
                    "source": r["source"],
                    "section": r["section"],
                    "doc_type": r["doc_type"],
                    "score": r["score"],
                    "collection": r["collection"],
                }
                for r in results
            ],
        }
    except Exception as e:
        logger.error(f"Document search failed: {e}")
        return {"query": q, "count": 0, "results": [], "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# GET /api/models — List Ollama models
# ═══════════════════════════════════════════════════════════════

@router.get("/models")
async def list_models():
    """List all models available in Ollama with details."""
    models = await ollama_service.list_models()
    return {
        "models": [
            {
                "name": m.get("name", ""),
                "size": _format_size(m.get("size", 0)),
                "parameter_size": m.get("details", {}).get("parameter_size", ""),
                "quantization": m.get("details", {}).get("quantization_level", ""),
                "modified_at": m.get("modified_at", ""),
            }
            for m in models
        ]
    }


# ═══════════════════════════════════════════════════════════════
# GET /api/health — System health check
# ═══════════════════════════════════════════════════════════════

@router.get("/health")
async def health():
    """
    System health check. Reports status of:
    - Ollama connection + available models
    - RAG subsystem (ChromaDB + embedding model + collection sizes)
    - Formal tools (sva2sby, SymbiYosys) — Phase 4
    """
    # Ollama status
    ollama_status = await ollama_service.health()

    # RAG status
    try:
        rag_health = await rag_service.health()
    except Exception as e:
        rag_health = {"chromadb": f"error: {e}", "collections": {}, "embedding_model": {}}

    # Formal tools status (Phase 4)
    sva2sby_available = "available" if shutil.which("sva2sby") else "not_installed"
    sby_available = "available" if shutil.which("sby") else "not_installed"

    return {
        "ollama": ollama_status["ollama"],
        "models": ollama_status["models"],
        "default_model": ollama_status["default_model"],
        "rag": {
            "chromadb": rag_health.get("chromadb", "unknown"),
            "collections": rag_health.get("collections", {}),
            "embedding_model": rag_health.get("embedding_model", {}),
        },
        "sva2sby": sva2sby_available,
        "sby": sby_available,
    }


# ═══════════════════════════════════════════════════════════════
# GET /api/docs/stats — RAG collection statistics
# ═══════════════════════════════════════════════════════════════

@router.get("/docs/stats")
async def docs_stats():
    """Return chunk counts per collection."""
    return rag_service.get_stats()


def _format_size(size_bytes: int) -> str:
    """Format bytes to human-readable string."""
    if size_bytes == 0:
        return "unknown"
    gb = size_bytes / (1024 ** 3)
    if gb >= 1:
        return f"{gb:.1f} GB"
    mb = size_bytes / (1024 ** 2)
    return f"{mb:.0f} MB"