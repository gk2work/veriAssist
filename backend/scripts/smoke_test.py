#!/usr/bin/env python3
"""
VeriAssist v2.0 — Phase 1 Smoke Test

Verifies: Ollama connection, model availability, chat endpoint,
all 5 modes, streaming, and response quality.

Usage: python scripts/smoke_test.py
"""

import httpx
import json
import time
import sys

BASE = "http://localhost:8000"
OLLAMA = "http://localhost:11434"


def check(name: str, ok: bool, detail: str = ""):
    status = "\033[92mPASS\033[0m" if ok else "\033[91mFAIL\033[0m"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def main():
    print("\n\033[1m=== VeriAssist v2.0 — Phase 1 Smoke Test ===\033[0m\n")
    results = []

    # 1. Ollama direct connection
    print("\033[1m1. Ollama Connection\033[0m")
    try:
        r = httpx.get(f"{OLLAMA}/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        results.append(check("Ollama reachable", True, f"{len(models)} models"))
        results.append(check("Models available", len(models) > 0, ", ".join(models[:3])))
    except Exception as e:
        results.append(check("Ollama reachable", False, str(e)))
        print("\n  \033[91mOllama not running. Start with: ollama serve\033[0m\n")
        sys.exit(1)

    # 2. Backend health
    print("\n\033[1m2. Backend Health\033[0m")
    try:
        r = httpx.get(f"{BASE}/api/health", timeout=5)
        data = r.json()
        results.append(check("Backend reachable", True))
        results.append(check("Ollama status via backend", data["ollama"] == "connected"))
        results.append(check("Default model set", bool(data["default_model"]), data["default_model"]))
        results.append(check("sva2sby status", True, data.get("sva2sby", "not checked")))
        results.append(check("sby status", True, data.get("sby", "not checked")))
    except Exception as e:
        results.append(check("Backend reachable", False, str(e)))
        print("\n  \033[91mBackend not running. Start with: uvicorn app.main:app --port 8000\033[0m\n")
        sys.exit(1)

    # 3. Models endpoint
    print("\n\033[1m3. Models Endpoint\033[0m")
    try:
        r = httpx.get(f"{BASE}/api/models", timeout=5)
        models = r.json()["models"]
        results.append(check("/api/models works", len(models) > 0, f"{len(models)} models"))
    except Exception as e:
        results.append(check("/api/models works", False, str(e)))

    # 4. Chat endpoint — test each mode
    print("\n\033[1m4. Chat Streaming (all 5 modes)\033[0m")
    test_prompts = {
        "chat": "What is uvm_config_db? Answer in 2 sentences.",
        "generate": "Write a simple UVM transaction class for a 32-bit data bus. Keep it short.",
        "sva": "Write an SVA property: ACK within 3 cycles of REQ. Keep it minimal.",
        "formal": "Write a formal-friendly SVA: data stable while valid is high. Keep it minimal.",
        "debug": "Explain this error: UVM_FATAL: no sequencer set for driver. Answer in 2 sentences.",
    }

    for mode, prompt in test_prompts.items():
        t0 = time.time()
        tokens = []
        first_token_time = None

        try:
            with httpx.stream(
                "POST",
                f"{BASE}/api/chat",
                json={"message": prompt, "mode": mode, "max_tokens": 256},
                timeout=httpx.Timeout(connect=5, read=120, write=10, pool=10),
            ) as r:
                for line in r.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = json.loads(line[6:])
                    if data.get("token"):
                        if first_token_time is None:
                            first_token_time = time.time() - t0
                        tokens.append(data["token"])
                    if data.get("done"):
                        break

            total = time.time() - t0
            text = "".join(tokens)
            tok_count = len(tokens)
            tps = tok_count / total if total > 0 else 0

            results.append(check(
                f"Mode: {mode}",
                tok_count > 5,
                f"{tok_count} tokens, first={first_token_time:.1f}s, total={total:.1f}s, {tps:.1f} tok/s"
            ))

            # Quality checks
            if mode == "formal" and ("$past" in text or "first_match" in text):
                results.append(check(
                    f"  Formal mode compliance",
                    False,
                    "Generated banned construct ($past or first_match)"
                ))

        except Exception as e:
            results.append(check(f"Mode: {mode}", False, str(e)))

    # Summary
    passed = sum(results)
    total = len(results)
    print(f"\n\033[1m{'='*50}\033[0m")
    print(f"\033[1mResults: {passed}/{total} passed\033[0m")
    if passed == total:
        print("\033[92m\nAll checks passed! Phase 1 is working.\033[0m\n")
    else:
        print(f"\033[91m\n{total - passed} checks failed. Review above.\033[0m\n")


if __name__ == "__main__":
    main()
