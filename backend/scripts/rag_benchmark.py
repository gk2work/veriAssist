#!/usr/bin/env python3
"""
VeriAssist v2.0 — RAG Quality Benchmark

Tests retrieval quality across 50 curated queries spanning:
- UVM methodology (10 queries)
- SystemVerilog language (10 queries)
- SVA assertions (10 queries)
- Formal verification / sva2sby (10 queries)
- Tool-specific / debug (10 queries)

Measures:
1. Retrieval hit rate: did we get ANY relevant results?
2. Top-1 relevance: is the best result actually relevant?
3. Source accuracy: did we retrieve from the right collection?
4. Latency: time per query (embed + retrieve)

Usage:
    python scripts/rag_benchmark.py               # Run all 50 queries
    python scripts/rag_benchmark.py --category sva # Run only SVA queries
    python scripts/rag_benchmark.py --verbose      # Show retrieved chunks
    python scripts/rag_benchmark.py --top-k 3      # Test with different top_k

Requires: ChromaDB populated (run ingest_docs.py first)
"""

import sys
import time
import asyncio
import logging
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.rag_service import rag_service, should_use_rag, get_rag_collections_for_mode

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("benchmark")

# ═══════════════════════════════════════════════════════════════
# 50 CURATED TEST QUERIES
# ═══════════════════════════════════════════════════════════════
# Each query: (category, query, expected_collection, expected_keywords)
# expected_keywords: words that SHOULD appear in a relevant result

BENCHMARK_QUERIES = [
    # ── UVM Methodology (10) ──────────────────────────────
    ("uvm", "What are the arguments to uvm_config_db::set?",
     "uvm_docs", ["uvm_config_db", "set", "cntxt", "inst_name"]),

    ("uvm", "How do I implement a virtual sequence that coordinates two agents?",
     "uvm_docs", ["virtual", "sequence", "sequencer", "agent"]),

    ("uvm", "What is the difference between uvm_component and uvm_object?",
     "uvm_docs", ["uvm_component", "uvm_object", "phase", "hierarchy"]),

    ("uvm", "How does the UVM factory override mechanism work?",
     "uvm_docs", ["factory", "override", "set_type_override", "set_inst_override"]),

    ("uvm", "Explain UVM phasing: build_phase, connect_phase, run_phase",
     "uvm_docs", ["build_phase", "connect_phase", "run_phase", "phase"]),

    ("uvm", "How do TLM analysis ports work for monitor to scoreboard?",
     "uvm_docs", ["analysis_port", "analysis_imp", "write", "monitor"]),

    ("uvm", "What is the UVM register model RAL?",
     "uvm_docs", ["register", "ral", "uvm_reg", "uvm_reg_block"]),

    ("uvm", "How to raise and drop objections in UVM?",
     "uvm_docs", ["raise_objection", "drop_objection", "phase", "objection"]),

    ("uvm", "What is the purpose of uvm_sequencer and how does it work?",
     "uvm_docs", ["sequencer", "sequence", "driver", "arbitration"]),

    ("uvm", "How to implement functional coverage in UVM?",
     "uvm_docs", ["covergroup", "coverpoint", "cross", "coverage"]),

    # ── SystemVerilog Language (10) ────────────────────────
    ("sv", "What is the difference between logic and reg in SystemVerilog?",
     "sv_lrm", ["logic", "reg", "wire", "4-state"]),

    ("sv", "How do SystemVerilog constraints work with rand variables?",
     "sv_lrm", ["rand", "constraint", "solve", "randomize"]),

    ("sv", "Explain SystemVerilog interfaces and modports",
     "sv_lrm", ["interface", "modport", "clocking", "port"]),

    ("sv", "What are SystemVerilog packages and how to import them?",
     "sv_lrm", ["package", "import", "export", "scope"]),

    ("sv", "How does the SystemVerilog mailbox work?",
     "sv_lrm", ["mailbox", "put", "get", "try_get", "bounded"]),

    ("sv", "Explain typedef enum in SystemVerilog",
     "sv_lrm", ["typedef", "enum", "state", "type"]),

    ("sv", "What are clocking blocks in SystemVerilog?",
     "sv_lrm", ["clocking", "input", "output", "skew", "default"]),

    ("sv", "How to use fork/join, fork/join_any, fork/join_none?",
     "sv_lrm", ["fork", "join", "join_any", "join_none", "parallel"]),

    ("sv", "What is $cast in SystemVerilog and when to use it?",
     "sv_lrm", ["cast", "dynamic", "parent", "child", "handle"]),

    ("sv", "How do parameterized classes work in SystemVerilog?",
     "sv_lrm", ["parameterized", "class", "type", "parameter"]),

    # ── SVA Assertions (10) ───────────────────────────────
    ("sva", "How to write an SVA property for AXI handshake?",
     "sva_patterns", ["axi", "valid", "ready", "|->", "handshake"]),

    ("sva", "What is the difference between |-> and |=> in SVA?",
     "sva_patterns", ["|->", "|=>", "overlapping", "non-overlapping"]),

    ("sva", "How to use $rose and $fell in SVA assertions?",
     "sva_patterns", ["$rose", "$fell", "edge", "posedge"]),

    ("sva", "Write SVA for data stability: data stable while valid is high",
     "sva_patterns", ["stable", "valid", "data", "$stable"]),

    ("sva", "How to write bounded repetition [*N] in SVA?",
     "sva_patterns", ["repetition", "[*", "consecutive", "bounded"]),

    ("sva", "SVA property: response within N clock cycles of request",
     "sva_patterns", ["##", "delay", "within", "cycles"]),

    ("sva", "How does disable iff work in SVA?",
     "sva_patterns", ["disable", "iff", "reset", "asynchronous"]),

    ("sva", "Write SVA assertions for FIFO overflow and underflow",
     "sva_patterns", ["fifo", "full", "empty", "overflow", "underflow"]),

    ("sva", "How to use goto repetition [->N] in SVA?",
     "sva_patterns", ["goto", "[->", "non-consecutive", "repetition"]),

    ("sva", "SVA cover property vs assert property — when to use which?",
     "sva_patterns", ["cover", "assert", "property", "reachability"]),

    # ── Formal Verification / sva2sby (10) ────────────────
    ("formal", "What SVA constructs does sva2sby support?",
     "tool_docs", ["sva2sby", "supported", "|->", "|=>", "##"]),

    ("formal", "How does sva2sby lower implication operators?",
     "tool_docs", ["sva2sby", "lower", "implication", "monitor", "RTL"]),

    ("formal", "What SVA constructs are NOT supported by sva2sby?",
     "tool_docs", ["sva2sby", "unsupported", "$past", "first_match", "intersect"]),

    ("formal", "How to run SymbiYosys bounded model checking?",
     "tool_docs", ["sby", "bmc", "bounded", "depth", "solver"]),

    ("formal", "What solvers does SymbiYosys support?",
     "tool_docs", ["boolector", "yices", "z3", "solver", "sby"]),

    ("formal", "How to write a SymbiYosys .sby configuration file?",
     "tool_docs", ["sby", "tasks", "engines", "script", "read"]),

    ("formal", "What is the difference between BMC and k-induction proof?",
     "tool_docs", ["bmc", "induction", "bounded", "unbounded", "prove"]),

    ("formal", "How does sva2sby handle range delays ##[M:N]?",
     "tool_docs", ["sva2sby", "range", "delay", "counter", "window"]),

    ("formal", "How to use cover mode in SymbiYosys?",
     "tool_docs", ["cover", "sby", "reachability", "trace", "vcd"]),

    ("formal", "What is the bind statement and how does sva2sby handle it?",
     "tool_docs", ["bind", "sva2sby", "checker", "dut", "rewriting"]),

    # ── Tool / Debug (10) ─────────────────────────────────
    ("debug", "UVM_FATAL: factory registration not found",
     "uvm_docs", ["factory", "registration", "uvm_component_utils", "override"]),

    ("debug", "Phase objection raised but never dropped — simulation hangs",
     "uvm_docs", ["objection", "raise", "drop", "timeout", "phase"]),

    ("debug", "Null object access in UVM scoreboard write method",
     "uvm_docs", ["null", "scoreboard", "analysis_imp", "build_phase"]),

    ("debug", "UVM sequence not starting — sequencer body not executing",
     "uvm_docs", ["sequence", "start", "body", "sequencer", "default_sequence"]),

    ("debug", "How to debug assertion failures in Xcelium?",
     "tool_docs", ["xcelium", "assertion", "debug", "waveform", "coverage"]),

    ("debug", "SymbiYosys returns UNKNOWN — what does it mean?",
     "tool_docs", ["sby", "unknown", "timeout", "depth", "increase"]),

    ("debug", "Formal counterexample VCD: how to read the waveform?",
     "tool_docs", ["vcd", "counterexample", "waveform", "trace", "cycle"]),

    ("debug", "Type mismatch error in SystemVerilog: cannot assign to logic",
     "sv_lrm", ["type", "mismatch", "logic", "assign", "cast"]),

    ("debug", "Covergroup instance is null at end of simulation",
     "uvm_docs", ["covergroup", "null", "new", "build_phase", "constructor"]),

    ("debug", "TLM port not connected error in UVM",
     "uvm_docs", ["tlm", "port", "connect", "analysis", "connect_phase"]),
]


# ═══════════════════════════════════════════════════════════════
# BENCHMARK RUNNER
# ═══════════════════════════════════════════════════════════════

async def run_benchmark(
    category: str = None,
    top_k: int = 5,
    verbose: bool = False,
):
    """Run the benchmark and report results."""

    # Filter queries by category
    queries = BENCHMARK_QUERIES
    if category:
        queries = [q for q in queries if q[0] == category]
        if not queries:
            print(f"No queries for category '{category}'")
            print(f"Available: uvm, sv, sva, formal, debug")
            return

    # Check if ChromaDB has data
    stats = rag_service.get_stats()
    total_chunks = stats.get("total", 0)
    if total_chunks == 0:
        print("\n\033[91mERROR: ChromaDB is empty. Run ingestion first:\033[0m")
        print("  python scripts/ingest_docs.py\n")
        return

    print(f"\n{'='*70}")
    print(f"  VeriAssist v2.0 — RAG Quality Benchmark")
    print(f"{'='*70}")
    print(f"  Queries:    {len(queries)}" + (f" (category: {category})" if category else " (all categories)"))
    print(f"  Top-k:      {top_k}")
    print(f"  DB chunks:  {total_chunks}")
    print(f"  Collections: {', '.join(f'{k}={v}' for k, v in stats.items() if k != 'total' and v > 0)}")
    print(f"{'='*70}\n")

    # Run each query
    results = []
    total_latency = 0

    for i, (cat, query, expected_col, expected_kw) in enumerate(queries):
        t0 = time.time()

        # Retrieve
        retrieved = await rag_service.retrieve(
            query=query,
            top_k=top_k,
        )

        latency = time.time() - t0
        total_latency += latency

        # Evaluate
        has_results = len(retrieved) > 0
        top1_text = retrieved[0]["text"] if has_results else ""
        top1_source = retrieved[0]["source"] if has_results else ""
        top1_collection = retrieved[0]["collection"] if has_results else ""
        top1_score = retrieved[0]["score"] if has_results else 0.0

        # Check keyword hits in top result
        top1_lower = top1_text.lower()
        kw_hits = sum(1 for kw in expected_kw if kw.lower() in top1_lower)
        kw_total = len(expected_kw)
        kw_ratio = kw_hits / kw_total if kw_total > 0 else 0

        # Check if correct collection
        correct_collection = top1_collection == expected_col

        # Score: relevant if >=50% keywords hit
        relevant = kw_ratio >= 0.5

        result = {
            "category": cat,
            "query": query,
            "has_results": has_results,
            "relevant": relevant,
            "correct_collection": correct_collection,
            "kw_ratio": kw_ratio,
            "top1_score": top1_score,
            "top1_source": top1_source,
            "top1_collection": top1_collection,
            "expected_collection": expected_col,
            "latency": latency,
            "num_results": len(retrieved),
        }
        results.append(result)

        # Print per-query result
        status = "\033[92mHIT\033[0m" if relevant else "\033[91mMISS\033[0m"
        col_status = "\033[92m✓\033[0m" if correct_collection else "\033[91m✗\033[0m"
        kw_str = f"{kw_hits}/{kw_total}"

        print(f"  [{status}] [{i+1:2d}/{ len(queries)}] ({cat:6s}) {query[:55]:55s}")
        print(f"         score={top1_score:.3f}  kw={kw_str:5s}  col={col_status} {top1_collection:12s}  {latency:.2f}s")

        if verbose and retrieved:
            print(f"         source: {top1_source}")
            preview = top1_text[:150].replace("\n", " ")
            print(f"         text: {preview}...")
            print()

    # ═══════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════
    total = len(results)
    hit_count = sum(1 for r in results if r["relevant"])
    col_correct = sum(1 for r in results if r["correct_collection"])
    has_any = sum(1 for r in results if r["has_results"])
    avg_score = sum(r["top1_score"] for r in results) / total if total > 0 else 0
    avg_kw = sum(r["kw_ratio"] for r in results) / total if total > 0 else 0
    avg_latency = total_latency / total if total > 0 else 0

    # Per-category breakdown
    categories = sorted(set(r["category"] for r in results))

    print(f"\n{'='*70}")
    print(f"  RESULTS SUMMARY")
    print(f"{'='*70}")
    print(f"\n  Overall:")
    print(f"    Retrieval hit rate:    {has_any}/{total} ({100*has_any/total:.0f}%)")
    print(f"    Relevance rate:        {hit_count}/{total} ({100*hit_count/total:.0f}%) — target: >90%")
    print(f"    Correct collection:    {col_correct}/{total} ({100*col_correct/total:.0f}%)")
    print(f"    Avg keyword overlap:   {100*avg_kw:.1f}%")
    print(f"    Avg similarity score:  {avg_score:.3f}")
    print(f"    Avg latency:           {avg_latency:.2f}s/query")
    print(f"    Total time:            {total_latency:.1f}s")

    print(f"\n  Per category:")
    for cat in categories:
        cat_results = [r for r in results if r["category"] == cat]
        cat_hits = sum(1 for r in cat_results if r["relevant"])
        cat_total = len(cat_results)
        bar = "\033[92m" + "█" * cat_hits + "\033[91m" + "█" * (cat_total - cat_hits) + "\033[0m"
        print(f"    {cat:8s}  {cat_hits}/{cat_total}  {bar}  ({100*cat_hits/cat_total:.0f}%)")

    # Grade
    rate = hit_count / total if total > 0 else 0
    if rate >= 0.9:
        grade = "\033[92mEXCELLENT\033[0m — RAG is production-ready"
    elif rate >= 0.75:
        grade = "\033[93mGOOD\033[0m — tune chunk sizes and add more docs"
    elif rate >= 0.5:
        grade = "\033[93mFAIR\033[0m — needs more documentation and tuning"
    else:
        grade = "\033[91mPOOR\033[0m — check ingestion, chunking, and embedding"

    print(f"\n  Grade: {grade}")

    # Suggestions
    if rate < 0.9:
        print(f"\n  Suggestions:")
        # Find weakest category
        worst_cat = min(categories, key=lambda c: sum(1 for r in results if r["category"] == c and r["relevant"]))
        worst_hits = sum(1 for r in results if r["category"] == worst_cat and r["relevant"])
        worst_total = sum(1 for r in results if r["category"] == worst_cat)
        print(f"    - Weakest category: {worst_cat} ({worst_hits}/{worst_total})")
        print(f"    - Add more {worst_cat} documentation to docs/ folder")
        if avg_score < 0.7:
            print(f"    - Avg score is low ({avg_score:.3f}) — try smaller chunk sizes (384 tokens)")
        if avg_latency > 2.0:
            print(f"    - Latency is high ({avg_latency:.2f}s) — check Ollama embedding performance")

    print(f"\n{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(description="VeriAssist RAG Benchmark")
    parser.add_argument("--category", choices=["uvm", "sv", "sva", "formal", "debug"],
                        help="Run only queries from this category")
    parser.add_argument("--top-k", type=int, default=5, help="Number of chunks to retrieve (default: 5)")
    parser.add_argument("--verbose", action="store_true", help="Show retrieved chunk text")

    args = parser.parse_args()
    asyncio.run(run_benchmark(args.category, args.top_k, args.verbose))


if __name__ == "__main__":
    main()