# VeriAssist Backend

FastAPI backend serving the VeriAssist VLSI assistant. Provides streaming LLM chat, RAG-augmented documentation lookup, SVA generation and validation, formal verification via SymbiYosys, UVM testbench generation, and coverage analysis.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

# Optional: ingest documentation into ChromaDB
python scripts/ingest_docs.py

uvicorn app.main:app --reload --port 8000
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Streaming chat (SSE) with RAG context |
| GET | `/api/models` | List available Ollama models |
| GET | `/api/health` | Ollama + RAG + formal tool status |
| GET | `/api/docs/search` | Direct RAG document search |
| POST | `/api/sva/generate` | Generate SVA from natural language |
| POST | `/api/sva/validate` | Validate SVA constructs |
| POST | `/api/formal/run` | Start async sby proof job |
| GET | `/api/formal/status/{job_id}` | Poll job status |
| POST | `/api/formal/run-sync` | Synchronous formal run |
| POST | `/api/formal/lower` | Lower SVA to .sby format |
| POST | `/api/uvm/generate` | Generate UVM components |
| POST | `/api/uvm/parse-interface` | Parse SystemVerilog interface |
| GET | `/api/uvm/protocols` | List supported protocols |
| POST | `/api/coverage/analyze` | Analyze DUT for coverage gaps |
| POST | `/api/coverage/generate` | Generate covergroup + UVM subscriber |
| POST | `/api/coverage/recommend` | Get sequence recommendations |

## Services

- **`llm_service.py`** — Async Ollama client with streaming support
- **`rag_service.py`** — ChromaDB retrieval across 4 knowledge collections
- **`embedding_service.py`** — nomic-embed-text embeddings via Ollama
- **`sva_lowering.py`** — Custom SVA → SymbiYosys `.sby` lowering engine
- **`formal_service.py`** — sby job management, result parsing, VCD handling
- **`uvm_generator.py`** — UVM component scaffolding and generation
- **`coverage_analyzer.py`** — FSM detection, signal classification, gap analysis
- **`coverage_generator.py`** — Covergroup and sequence code generation
- **`prompt_templates.py`** — Mode-specific system prompts

## Environment

Requires Ollama running at `http://localhost:11434`. Set `OLLAMA_BASE_URL` to override.

Requires `sby` (SymbiYosys) on PATH for formal verification modes.
