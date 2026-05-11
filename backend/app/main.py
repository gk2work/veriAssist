"""
VeriAssist v2.0 — FastAPI Application Entry Point

Run with: uvicorn app.main:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import chat, sva, formal, uvm, coverage
from app.services.llm_service import ollama_service
from app.services.embedding_service import embedding_service
from app.services.rag_service import rag_service
from app.services.formal_service import formal_service

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("chromadb.telemetry").setLevel(logging.CRITICAL)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger("veriassist")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("VeriAssist v2.0 starting...")

    # Check Ollama
    status = await ollama_service.health()
    if status["ollama"] == "connected":
        logger.info(f"Ollama connected. Models: {status['models']}")
        logger.info(f"Default model: {status['default_model']}")
    else:
        logger.warning("Ollama not connected! Start it with: ollama serve")

    # Check RAG
    rag_stats = rag_service.get_stats()
    total_chunks = rag_stats.get("total", 0)
    if total_chunks > 0:
        logger.info(f"RAG knowledge base: {total_chunks} chunks across {sum(1 for v in rag_stats.values() if isinstance(v, int) and v > 0 and v != total_chunks)} collections")
    else:
        logger.warning("RAG knowledge base is empty. Run: python scripts/ingest_docs.py")

    # Check Formal tools
    formal_health = formal_service.health()
    if formal_health["sby"] == "available":
        logger.info(f"Formal tools: sby={formal_health['sby_path']}")
    else:
        logger.warning("SymbiYosys (sby) not found. Formal verification unavailable.")

    logger.info("VeriAssist v2.0 ready. Phases 1-7 active.")

    yield

    await ollama_service.close()
    await embedding_service.close()
    logger.info("VeriAssist shutdown complete.")


app = FastAPI(
    title="VeriAssist v2.0",
    description="On-Device VLSI Design Assistant with Formal Verification, UVM Generation, and Coverage Advisor",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(chat.router)
app.include_router(sva.router)
app.include_router(formal.router)
app.include_router(uvm.router)
app.include_router(coverage.router)


@app.get("/")
async def root():
    return {
        "name": "VeriAssist",
        "version": "2.0.0",
        "description": "On-Device VLSI Design Assistant",
        "phases": {
            "1": "Core Chat Engine",
            "2": "RAG Pipeline",
            "3": "SVA Generation",
            "4": "Formal Verification (SVA Lowering + SymbiYosys)",
            "5": "AI Counterexample Debug",
            "6": "UVM Testbench Generator",
            "7": "Coverage Advisor",
        },
        "endpoints": {
            "chat": "/api/chat",
            "docs_search": "/api/docs/search",
            "models": "/api/models",
            "health": "/api/health",
            "sva_generate": "/api/sva/generate",
            "sva_validate": "/api/sva/validate",
            "formal_run": "/api/formal/run",
            "formal_run_sync": "/api/formal/run-sync",
            "formal_lower": "/api/formal/lower",
            "formal_validate_rtl": "/api/formal/validate-rtl",
            "formal_debug": "/api/formal/debug/{job_id}",
            "formal_rerun": "/api/formal/rerun",
            "formal_status": "/api/formal/status/{job_id}",
            "formal_jobs": "/api/formal/jobs",
            "formal_health": "/api/formal/health",
            "uvm_generate": "/api/uvm/generate",
            "uvm_parse": "/api/uvm/parse-interface",
            "uvm_protocols": "/api/uvm/protocols",
            "coverage_analyze": "/api/coverage/analyze",
            "coverage_generate": "/api/coverage/generate",
            "coverage_recommend": "/api/coverage/recommend",
            "coverage_protocols": "/api/coverage/protocols",
        },
        "docs": "/docs",
    }
