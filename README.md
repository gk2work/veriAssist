# VeriAssist v2.0

> On-device VLSI design assistant with formal verification, UVM generation, SVA writing, and coverage analysis — powered by local LLMs via Ollama. No cloud, no API costs, runs entirely on your machine.

![VeriAssist](https://img.shields.io/badge/version-2.0-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![React](https://img.shields.io/badge/react-18-61dafb)

---

## What It Does

VeriAssist is a 7-mode AI workbench for chip and verification engineers:

| Mode | Purpose |
|------|---------|
| **Chat** | General VLSI / UVM Q&A with RAG-augmented answers |
| **Docs** | Documentation lookup across UVM LRM, SV LRM, SVA patterns |
| **Generate** | Full UVM testbench generation (agent, driver, monitor, scoreboard, sequences) |
| **SVA** | SystemVerilog assertion writing with construct validation |
| **Formal** | SVA lowering to SymbiYosys `.sby` format + automated proof runs |
| **Debug** | Error analysis, UVM fatal/warning triage, counterexample explanation |
| **Formal Verification** | File-based formal verification with property table and waveform output |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   React Frontend                    │
│  ActivityBar · Sidebar · ChatPanel · SpecialPanels  │
└────────────────────┬────────────────────────────────┘
                     │ HTTP / SSE
┌────────────────────▼────────────────────────────────┐
│               FastAPI Backend (:8000)               │
│  /api/chat  /api/sva  /api/formal  /api/uvm         │
│  /api/coverage  /api/models  /api/health            │
└──────┬─────────────┬──────────────┬─────────────────┘
       │             │              │
  ┌────▼────┐  ┌─────▼──────┐ ┌────▼────────┐
  │ Ollama  │  │  ChromaDB  │ │ SymbiYosys  │
  │  LLM   │  │    RAG     │ │    (sby)    │
  └─────────┘  └────────────┘ └─────────────┘
```

**Key design principle:** Everything runs locally. No data leaves your machine.

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- [Ollama](https://ollama.com/download) installed and running
- [SymbiYosys](https://symbiyosys.readthedocs.io/) (optional, for formal verification)

### 1 — Pull Models

```bash
# Start Ollama
ollama serve

# Primary model (fast, works on 8 GB RAM)
ollama pull qwen2.5-coder:3b-instruct

# Embedding model (required for RAG / Docs mode)
ollama pull nomic-embed-text

# Optional: larger model for better quality (needs 16 GB RAM)
ollama pull qwen2.5-coder:7b-instruct-q4_K_M
```

### 2 — Backend

```bash
cd backend

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt

# (Optional) Ingest documentation into ChromaDB
python scripts/ingest_docs.py

# Start the API server
uvicorn app.main:app --reload --port 8000
```

Expected output:
```
INFO: VeriAssist v2.0 starting...
INFO: Ollama connected. Models: ['qwen2.5-coder:3b-instruct', 'nomic-embed-text:latest']
INFO: Default model: qwen2.5-coder:3b-instruct
INFO: RAG knowledge base: 3478 chunks across 4 collections
INFO: Formal tools: sby=/usr/local/bin/sby
INFO: VeriAssist v2.0 ready. Phases 1-7 active.
```

### 3 — Frontend

```bash
cd frontend

npm install
npm run dev
# Opens at http://localhost:5173
```

---

## Project Structure

```
veriAssist/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI entry point + lifespan
│   │   ├── routers/
│   │   │   ├── chat.py                # /api/chat, /api/models, /api/health
│   │   │   ├── sva.py                 # /api/sva/generate, /api/sva/validate
│   │   │   ├── formal.py              # /api/formal/run, /api/formal/status
│   │   │   ├── uvm.py                 # /api/uvm/generate, /api/uvm/protocols
│   │   │   └── coverage.py            # /api/coverage/analyze, /api/coverage/generate
│   │   ├── services/
│   │   │   ├── llm_service.py         # Ollama streaming wrapper
│   │   │   ├── rag_service.py         # ChromaDB retrieval
│   │   │   ├── embedding_service.py   # nomic-embed-text embeddings
│   │   │   ├── sva_lowering.py        # SVA → SymbiYosys lowering engine
│   │   │   ├── formal_service.py      # sby job runner + result parser
│   │   │   ├── uvm_generator.py       # UVM component code generation
│   │   │   ├── coverage_analyzer.py   # DUT FSM/signal analysis
│   │   │   ├── coverage_generator.py  # Covergroup + sequence generation
│   │   │   ├── prompt_templates.py    # Mode-specific system prompts
│   │   │   └── sva_parser.py          # SVA construct parser/validator
│   │   └── models/
│   │       └── schemas.py             # Pydantic request/response models
│   ├── scripts/
│   │   ├── ingest_docs.py             # Load docs into ChromaDB
│   │   ├── smoke_test.py              # Integration test for all modes
│   │   ├── formal_eval.py             # Formal verification evaluation
│   │   ├── uvm_eval.py                # UVM generation evaluation
│   │   ├── sva_eval.py                # SVA generation evaluation
│   │   └── coverage_eval.py           # Coverage analysis evaluation
│   └── requirements.txt
│
└── frontend/
    ├── src/
    │   ├── App.jsx                    # Root layout: ActivityBar + Sidebar + panels
    │   ├── theme.js                   # Design tokens (colors, fonts, spacing)
    │   ├── components/
    │   │   ├── Sidebar.jsx            # Collapsible mode nav + model + temperature
    │   │   ├── ChatPanel.jsx          # Streaming chat UI (chat/docs/sva/debug)
    │   │   ├── FormalPanel.jsx        # SVA + SymbiYosys formal panel
    │   │   ├── FVPanel.jsx            # File-based formal verification panel
    │   │   ├── GeneratePanel.jsx      # UVM testbench generator panel
    │   │   ├── CoveragePanel.jsx      # Coverage advisor panel
    │   │   └── CodeViewer.jsx         # Syntax-highlighted code display
    │   ├── hooks/
    │   │   └── useVeriAssist.js       # Central state + API hook
    │   └── config/
    │       └── constants.js           # Modes, prompts, formal config
    ├── package.json
    └── vite.config.js
```

---

## API Reference

### POST `/api/chat`
Streaming chat with RAG-augmented context.

```json
{
  "message": "Generate a UVM driver for AXI4-Lite",
  "history": [],
  "mode": "generate",
  "model": "qwen2.5-coder:3b-instruct",
  "temperature": 0.3,
  "max_tokens": 4096
}
```

Returns Server-Sent Events:
```
data: {"token": "class", "done": false}
data: {"token": " axi_driver", "done": false}
...
data: {"token": "", "done": true, "sources": [...]}
```

### POST `/api/sva/generate`
Generate SVA properties from natural language.

### POST `/api/formal/run`
Run SymbiYosys formal proof on an SVA property. Returns a job ID for polling.

### GET `/api/formal/status/{job_id}`
Poll formal verification job status and results.

### POST `/api/uvm/generate`
Generate complete UVM testbench components from interface description.

### POST `/api/coverage/analyze`
Analyze DUT SystemVerilog for coverage gaps (FSM states, signal boundaries, protocol-specific points).

### POST `/api/coverage/generate`
Generate a complete SystemVerilog covergroup + UVM subscriber from DUT analysis.

### GET `/api/health`
System health — Ollama connection, available models, RAG stats, formal tool availability.

### GET `/api/models`
List all Ollama models with size and quantization details.

---

## RAG Knowledge Base

The Docs mode and chat context are augmented by a ChromaDB vector store with 4 collections:

| Collection | Contents |
|-----------|---------|
| `uvm_docs` | UVM 1.2 class reference, phase guide, TLM documentation |
| `sv_lrm` | SystemVerilog LRM excerpts (interfaces, clocking blocks, assertions) |
| `sva_patterns` | SVA pattern library for common protocols |
| `tool_docs` | SymbiYosys configuration and solver documentation |

Run `python scripts/ingest_docs.py` after placing source PDFs in `backend/docs/`.

---

## Formal Verification Flow

```
Natural language spec
        │
        ▼
  SVA Generation (LLM)
        │
        ▼
  SVA Validation (parser checks sva2sby-compatible constructs)
        │
        ▼
  SVA Lowering (custom engine → .sby file)
        │
        ▼
  SymbiYosys BMC / k-induction run
        │
        ▼
  PASS / FAIL + counterexample trace
        │
        ▼
  AI counterexample explanation (Debug mode)
```

Supported solvers: Boolector (default), Yices 2, Z3
Supported protocols: AXI4, AXI4-Lite, AHB, APB, SPI, I2C, UART, FIFO, FSM

---

## Dependencies

### Backend
| Package | Purpose |
|---------|---------|
| `fastapi` | REST API framework |
| `uvicorn` | ASGI server |
| `httpx` | Async Ollama client |
| `chromadb` | Vector database for RAG |
| `langchain` | Document loading and text splitting |
| `pypdf` | PDF ingestion |
| `pyvcd` | VCD waveform parsing |
| `pydantic` | Request/response validation |

### Frontend
| Package | Purpose |
|---------|---------|
| `react` | UI framework |
| `vite` | Build tool + dev server |

### External Tools
| Tool | Purpose | Install |
|------|---------|---------|
| Ollama | Local LLM runtime | `brew install ollama` |
| SymbiYosys | Formal verification | [docs](https://symbiyosys.readthedocs.io/) |
| Boolector / Yices / Z3 | SMT solvers (used by sby) | via package manager |

---

## Model Recommendations

| RAM | Recommended Model | Speed |
|-----|------------------|-------|
| 8 GB | `qwen2.5-coder:3b-instruct` | ~30 tok/s |
| 16 GB | `qwen2.5-coder:7b-instruct-q4_K_M` | ~12 tok/s |
| 32 GB+ | `qwen2.5-coder:14b-instruct-q4_K_M` | ~8 tok/s |

Or run Ollama in Docker:
```bash
docker run -d -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama
docker exec -it ollama ollama pull qwen2.5-coder:3b-instruct
```

---

## Development

```bash
# Run backend smoke test (tests all 7 modes)
cd backend && python scripts/smoke_test.py

# Check API health
curl http://localhost:8000/api/health | python3 -m json.tool

# Frontend lint
cd frontend && npm run lint
```

---

## Author

**Gautam Kumar** — Built as an on-device VLSI productivity tool.  
Phases 1–7: Core Chat → RAG → SVA → Formal Verification → AI Debug → UVM Generation → Coverage Advisor
