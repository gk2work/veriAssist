#!/usr/bin/env python3
"""
VeriAssist v2.0 — SVA Generation Evaluation

Tests SVA generation quality across 30 prompts covering:
- Implication operators (|-> |=>)
- Delay operators (##N, ##[M:N])
- Repetition ([*N], [->N], [=N])
- System functions ($rose, $fell, $stable, $changed)
- Reset/clock handling (disable iff, default clocking)
- Protocol-specific (AXI, APB, FIFO, FSM)
- Edge cases (parameterized, bind, cover-only)

Measures:
1. Code extraction rate — did we get a code block?
2. Syntax correctness — structural validation passes?
3. sva2sby compatibility — no banned constructs?
4. Formal readiness — has assert/cover, clocking, reset?
5. Semantic checks — expected keywords present in output?
6. Latency — generation time per prompt

Usage:
    python scripts/sva_eval.py                  # Run all 30 prompts
    python scripts/sva_eval.py --category axi   # Run only AXI prompts
    python scripts/sva_eval.py --verbose         # Show generated code
    python scripts/sva_eval.py --no-retry        # Disable auto-retry

Requires: Backend running on port 8000, Ollama serving
"""

import sys
import time
import json
import httpx
import logging
import argparse
from pathlib import Path

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("sva_eval")

API_BASE = "http://localhost:8000"

# ═══════════════════════════════════════════════════════════════
# 30 TEST PROMPTS
# ═══════════════════════════════════════════════════════════════
# (category, description, mode, expected_constructs, expected_keywords, protocol)

EVAL_PROMPTS = [
    # ── Implication Operators (4) ─────────────────────────
    ("implication", "When req is high, gnt must be high in the same cycle",
     "formal", ["overlapping_implication"], ["req", "gnt", "|->"], None),

    ("implication", "When write_en is asserted, data_valid must be asserted the next cycle",
     "formal", ["non_overlapping_implication"], ["write_en", "data_valid", "|=>"], None),

    ("implication", "If start is high, then busy must go high next cycle and stay high until done",
     "formal", ["non_overlapping_implication"], ["start", "busy", "done", "|=>"], None),

    ("implication", "When chip_select is low, data bus must be high impedance (all zeros) in the same cycle",
     "formal", ["overlapping_implication"], ["chip_select", "|->"], None),

    # ── Delay Operators (4) ───────────────────────────────
    ("delay", "ACK must arrive exactly 3 cycles after REQ goes high",
     "formal", ["fixed_delay", "rose"], ["req", "ack", "##3", "$rose"], None),

    ("delay", "Response must arrive within 1 to 8 cycles after request",
     "formal", ["range_delay"], ["##[1:8]", "response", "request"], None),

    ("delay", "After reset deasserts, ready must be high within 5 cycles",
     "formal", ["range_delay", "rose"], ["rst", "ready", "##"], None),

    ("delay", "After grant is asserted, data must be valid exactly 2 cycles later and stable for 3 cycles",
     "formal", ["fixed_delay"], ["grant", "data", "##2"], None),

    # ── Repetition (4) ────────────────────────────────────
    ("repetition", "Data valid must be asserted for exactly 4 consecutive cycles after start",
     "formal", ["bounded_repetition"], ["data_valid", "[*4]", "start"], None),

    ("repetition", "After request, there must be exactly 3 acknowledgments (not necessarily consecutive) before done",
     "formal", ["goto_repetition"], ["ack", "[->3]", "request"], None),

    ("repetition", "The busy signal must remain high for between 2 and 8 consecutive cycles",
     "formal", ["bounded_repetition"], ["busy", "[*"], None),

    ("repetition", "After enable, the ready signal must pulse high exactly 2 times non-consecutively before complete",
     "formal", ["nonconsec_repetition"], ["ready", "[=2]", "enable"], None),

    # ── System Functions (4) ──────────────────────────────
    ("sysfunc", "Detect rising edge of interrupt and verify handler responds within 10 cycles",
     "formal", ["rose", "range_delay"], ["$rose", "interrupt", "handler", "##"], None),

    ("sysfunc", "When valid is high, data bus must remain stable",
     "formal", ["stable"], ["$stable", "valid", "data"], None),

    ("sysfunc", "Detect falling edge of enable and verify output goes low within 2 cycles",
     "formal", ["fell", "range_delay"], ["$fell", "enable", "output"], None),

    ("sysfunc", "After write enable, the address must change on the next cycle",
     "formal", ["changed", "non_overlapping_implication"], ["$changed", "addr", "wr_en"], None),

    # ── AXI Protocol (5) ──────────────────────────────────
    ("axi", "AWVALID must remain asserted until AWREADY is asserted",
     "formal", ["non_overlapping_implication"], ["awvalid", "awready", "|=>"], "axi"),

    ("axi", "AWREADY must respond within 16 cycles of AWVALID going high",
     "formal", ["rose", "range_delay"], ["awvalid", "awready", "$rose", "##"], "axi"),

    ("axi", "Write data must be stable while WVALID is high and WREADY is low",
     "formal", ["stable"], ["wvalid", "wready", "$stable", "wdata"], "axi"),

    ("axi", "Write response BVALID must arrive within 32 cycles after write data handshake completes",
     "formal", ["range_delay"], ["bvalid", "wvalid", "wready", "##"], "axi"),

    ("axi", "Generate a complete parameterized handshake checker that works for any AXI channel",
     "formal", ["non_overlapping_implication"], ["property", "valid", "ready", "assert"], "axi"),

    # ── APB Protocol (2) ──────────────────────────────────
    ("apb", "PENABLE must assert exactly one cycle after PSEL goes high",
     "formal", ["rose", "fixed_delay"], ["psel", "penable", "$rose", "##1"], "apb"),

    ("apb", "Address and control signals must remain stable during entire APB transfer while PSEL is high",
     "formal", ["stable"], ["psel", "paddr", "$stable"], "apb"),

    # ── FIFO (3) ──────────────────────────────────────────
    ("fifo", "Write enable must never be asserted when FIFO is full",
     "formal", ["overlapping_implication"], ["full", "wr_en", "|->"], "fifo"),

    ("fifo", "Read enable must never be asserted when FIFO is empty",
     "formal", ["overlapping_implication"], ["empty", "rd_en", "|->"], "fifo"),

    ("fifo", "FIFO full flag must be asserted when count equals depth parameter, and empty when count is zero",
     "formal", ["overlapping_implication"], ["full", "empty", "count"], "fifo"),

    # ── FSM (2) ───────────────────────────────────────────
    ("fsm", "FSM must never enter an illegal state outside the defined encoding IDLE ADDR DATA RESP DONE",
     "formal", [], ["state", "IDLE", "ADDR", "assert"], None),

    ("fsm", "After reaching DONE state, FSM must return to IDLE within 2 cycles",
     "formal", ["range_delay"], ["state", "DONE", "IDLE", "##"], None),

    # ── Edge Cases (2) ────────────────────────────────────
    ("edge", "Generate only cover properties to check that all FSM states are reachable from reset",
     "formal", [], ["cover", "property", "state"], None),

    ("edge", "Generate assertions with a bind statement to attach checker to module my_dut",
     "formal", [], ["bind", "my_dut", "assert"], None),
]


# ═══════════════════════════════════════════════════════════════
# EVALUATION RUNNER
# ═══════════════════════════════════════════════════════════════

def run_eval(category: str = None, verbose: bool = False, auto_retry: bool = True):
    """Run SVA generation evaluation."""

    prompts = EVAL_PROMPTS
    if category:
        prompts = [p for p in prompts if p[0] == category]
        if not prompts:
            cats = sorted(set(p[0] for p in EVAL_PROMPTS))
            print(f"No prompts for category '{category}'")
            print(f"Available: {', '.join(cats)}")
            return

    # Check backend is running
    try:
        r = httpx.get(f"{API_BASE}/api/health", timeout=5)
        health = r.json()
        if health.get("ollama") != "connected":
            print("ERROR: Ollama not connected. Start it with: ollama serve")
            return
    except Exception:
        print("ERROR: Backend not reachable. Start it with: uvicorn app.main:app --port 8000")
        return

    print(f"\n{'='*70}")
    print(f"  VeriAssist v2.0 — SVA Generation Evaluation")
    print(f"{'='*70}")
    print(f"  Prompts:     {len(prompts)}" + (f" (category: {category})" if category else " (all)"))
    print(f"  Auto-retry:  {'enabled' if auto_retry else 'disabled'}")
    print(f"  Model:       {health.get('default_model', 'unknown')}")
    print(f"{'='*70}\n")

    results = []
    total_time = 0

    for i, (cat, desc, mode, expected_constructs, expected_kw, protocol) in enumerate(prompts):
        print(f"  [{i+1:2d}/{len(prompts)}] ({cat:12s}) {desc[:55]}...")

        t0 = time.time()

        try:
            payload = {
                "description": desc,
                "mode": mode,
                "protocol": protocol,
                "auto_retry": auto_retry,
                "stream": False,
            }
            resp = httpx.post(
                f"{API_BASE}/api/sva/generate",
                json=payload,
                timeout=httpx.Timeout(connect=5, read=120, write=10, pool=10),
            )
            data = resp.json()
        except Exception as e:
            print(f"         \033[91mFAIL\033[0m — request error: {e}")
            results.append(_fail_result(cat, desc))
            continue

        latency = time.time() - t0
        total_time += latency

        sva_code = data.get("sva_code", "")
        validation = data.get("validation", {})
        retried = data.get("retried", False)

        # ── Evaluate ──────────────────────────────────────
        has_code = bool(sva_code.strip())
        is_valid = validation.get("valid", False)
        is_compatible = validation.get("sva2sby_compatible", False)
        errors = validation.get("errors", [])
        warnings = validation.get("warnings", [])
        banned = validation.get("banned_constructs", [])
        stats = validation.get("stats", {})

        # Keyword check
        code_lower = sva_code.lower()
        kw_hits = sum(1 for kw in expected_kw if kw.lower() in code_lower)
        kw_total = len(expected_kw)
        kw_ratio = kw_hits / kw_total if kw_total > 0 else 1.0
        semantic_pass = kw_ratio >= 0.5

        # Construct check
        detected = stats.get("constructs_used", [])
        construct_hits = sum(1 for c in expected_constructs if c in detected)
        construct_total = len(expected_constructs)
        construct_pass = construct_hits == construct_total if construct_total > 0 else True

        # Has formal elements
        has_assert = stats.get("assertions", 0) > 0 or stats.get("assumptions", 0) > 0 or stats.get("covers", 0) > 0
        has_clock = stats.get("has_default_clocking", False) or "@(posedge" in sva_code.lower()
        has_reset = stats.get("has_disable_iff", False)

        # Overall score
        score = sum([
            has_code,           # 1 point: got code
            is_valid,           # 1 point: structurally valid
            is_compatible,      # 1 point: sva2sby compatible
            semantic_pass,      # 1 point: expected keywords present
            construct_pass,     # 1 point: expected constructs used
            has_assert,         # 1 point: has assert/cover
            has_clock,          # 1 point: has clocking
            has_reset,          # 1 point: has reset handling
        ])
        max_score = 8
        pass_threshold = 6  # 6/8 = PASS

        is_pass = score >= pass_threshold

        result = {
            "category": cat,
            "description": desc,
            "has_code": has_code,
            "valid": is_valid,
            "sva2sby_compatible": is_compatible,
            "semantic_pass": semantic_pass,
            "construct_pass": construct_pass,
            "has_formal_elements": has_assert,
            "has_clock": has_clock,
            "has_reset": has_reset,
            "score": score,
            "max_score": max_score,
            "is_pass": is_pass,
            "retried": retried,
            "latency": latency,
            "errors": errors,
            "banned": banned,
            "kw_ratio": kw_ratio,
        }
        results.append(result)

        # Print result
        status = "\033[92mPASS\033[0m" if is_pass else "\033[91mFAIL\033[0m"
        retry_tag = " \033[93m(retried)\033[0m" if retried else ""
        compat_tag = "\033[92msby:✓\033[0m" if is_compatible else "\033[91msby:✗\033[0m"

        print(f"         [{status}] {score}/{max_score}  {compat_tag}  kw={kw_hits}/{kw_total}  {latency:.1f}s{retry_tag}")

        if not is_pass and (errors or banned):
            for e in errors[:2]:
                print(f"           \033[91m• {e}\033[0m")
            for b in banned[:2]:
                print(f"           \033[91m• Banned: {b}\033[0m")

        if verbose and has_code:
            preview = sva_code[:300].replace("\n", "\n           ")
            print(f"           Code: {preview}...")
            print()

    # ═══════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════
    total = len(results)
    passed = sum(1 for r in results if r["is_pass"])
    code_rate = sum(1 for r in results if r["has_code"]) / total * 100
    valid_rate = sum(1 for r in results if r["valid"]) / total * 100
    compat_rate = sum(1 for r in results if r["sva2sby_compatible"]) / total * 100
    semantic_rate = sum(1 for r in results if r["semantic_pass"]) / total * 100
    retry_count = sum(1 for r in results if r["retried"])
    avg_score = sum(r["score"] for r in results) / total
    avg_latency = total_time / total

    categories = sorted(set(r["category"] for r in results))

    print(f"\n{'='*70}")
    print(f"  EVALUATION RESULTS")
    print(f"{'='*70}")
    print(f"\n  Overall: {passed}/{total} passed ({100*passed/total:.0f}%) — target: >80%")
    print(f"\n  Breakdown:")
    print(f"    Code extraction rate:    {code_rate:.0f}%")
    print(f"    Syntax correctness:      {valid_rate:.0f}%  — target: >85%")
    print(f"    sva2sby compatibility:   {compat_rate:.0f}%  — target: >90%")
    print(f"    Semantic accuracy:       {semantic_rate:.0f}%")
    print(f"    Average score:           {avg_score:.1f}/{results[0]['max_score'] if results else 8}")
    print(f"    Auto-retries used:       {retry_count}/{total}")
    print(f"    Avg latency:             {avg_latency:.1f}s/prompt")
    print(f"    Total time:              {total_time:.0f}s")

    print(f"\n  Per category:")
    for cat in categories:
        cat_results = [r for r in results if r["category"] == cat]
        cat_passed = sum(1 for r in cat_results if r["is_pass"])
        cat_total = len(cat_results)
        cat_compat = sum(1 for r in cat_results if r["sva2sby_compatible"])
        bar = "\033[92m" + "█" * cat_passed + "\033[91m" + "█" * (cat_total - cat_passed) + "\033[0m"
        print(f"    {cat:12s}  {cat_passed}/{cat_total}  {bar}  sby:{cat_compat}/{cat_total}")

    # Grade
    rate = passed / total if total > 0 else 0
    if rate >= 0.9:
        grade = "\033[92mEXCELLENT\033[0m — SVA generation is production-ready"
    elif rate >= 0.8:
        grade = "\033[92mGOOD\033[0m — meets target, minor prompt tuning can improve further"
    elif rate >= 0.6:
        grade = "\033[93mFAIR\033[0m — needs prompt refinement or more few-shot examples"
    else:
        grade = "\033[91mPOOR\033[0m — check model, prompts, and RAG retrieval"

    print(f"\n  Grade: {grade}")

    # Specific suggestions
    if compat_rate < 90:
        failed_compat = [r for r in results if not r["sva2sby_compatible"]]
        if failed_compat:
            banned_names = set()
            for r in failed_compat:
                for b in r.get("banned", []):
                    name = b.split("(")[0].strip()
                    banned_names.add(name)
            if banned_names:
                print(f"\n  sva2sby issues — LLM is generating these banned constructs:")
                for name in sorted(banned_names):
                    print(f"    • {name}")
                print(f"    → Strengthen the BANNED CONSTRUCTS section in the formal mode prompt")

    if semantic_rate < 80:
        print(f"\n  Semantic issues — LLM is not using expected constructs:")
        weak = [r for r in results if not r["semantic_pass"]]
        for r in weak[:3]:
            print(f"    • {r['category']}: {r['description'][:50]}...")

    print(f"\n{'='*70}\n")


def _fail_result(cat, desc):
    """Create a failed result entry for request errors."""
    return {
        "category": cat, "description": desc,
        "has_code": False, "valid": False, "sva2sby_compatible": False,
        "semantic_pass": False, "construct_pass": False,
        "has_formal_elements": False, "has_clock": False, "has_reset": False,
        "score": 0, "max_score": 8, "is_pass": False,
        "retried": False, "latency": 0, "errors": ["Request failed"],
        "banned": [], "kw_ratio": 0,
    }


def main():
    parser = argparse.ArgumentParser(description="VeriAssist SVA Generation Evaluation")
    parser.add_argument("--category", type=str,
                        help="Run only prompts from this category")
    parser.add_argument("--verbose", action="store_true",
                        help="Show generated SVA code")
    parser.add_argument("--no-retry", action="store_true",
                        help="Disable auto-retry on validation failure")

    args = parser.parse_args()
    run_eval(
        category=args.category,
        verbose=args.verbose,
        auto_retry=not args.no_retry,
    )


if __name__ == "__main__":
    main()