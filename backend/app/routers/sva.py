"""
VeriAssist v2.0 — SVA Generation Router

POST /api/sva/generate  — Generate SVA from natural language description
                          with RAG-powered few-shot examples, validation,
                          sva2sby compatibility checking, and auto-retry.

Pipeline:
  1. Retrieve relevant SVA patterns from ChromaDB (few-shot examples)
  2. Build prompt: system + few-shot examples + user description
  3. LLM generates SVA code
  4. Extract code block from LLM response
  5. Validate: structural + sva2sby compatibility
  6. If invalid, auto-retry once with error feedback
  7. Return code + validation result + sources
"""

import json
import logging
from typing import Optional
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.llm_service import ollama_service
from app.services.rag_service import rag_service
from app.services.prompt_templates import get_system_prompt
from app.services.sv_validator import (
    validate_sva_for_formal,
    validate_sv,
    check_sva2sby_compatible,
    extract_sva_code,
    build_retry_prompt,
    build_validation_payload,
    ValidationResult,
)

logger = logging.getLogger("veriassist.sva")
router = APIRouter(prefix="/api/sva", tags=["sva"])


# ═══════════════════════════════════════════════════════════════
# REQUEST / RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════

class SVAGenerateRequest(BaseModel):
    description: str
    clock: str = "clk"
    reset: str = "rst_n"
    protocol: Optional[str] = None
    dut_module: Optional[str] = None
    dut_signals: list[str] = Field(default_factory=list)
    mode: str = "formal"  # "formal" (sva2sby constrained) or "sva" (general)
    model: Optional[str] = None
    temperature: float = 0.2  # lower than chat for precise code gen
    max_tokens: int = 4096
    auto_retry: bool = True  # auto-retry if validation fails
    stream: bool = False  # if True, stream tokens via SSE


class SVAGenerateResponse(BaseModel):
    sva_code: str
    full_response: str
    validation: dict
    sva2sby_compatible: bool
    sources: list[dict]
    retried: bool = False
    retry_reason: Optional[str] = None


# ═══════════════════════════════════════════════════════════════
# POST /api/sva/generate
# ═══════════════════════════════════════════════════════════════

@router.post("/generate")
async def generate_sva(req: SVAGenerateRequest):
    """
    Generate SVA assertions from natural language description.

    If stream=True, returns SSE stream (same format as /api/chat).
    If stream=False (default), returns complete SVAGenerateResponse.
    """
    if req.stream:
        return await _generate_streaming(req)
    else:
        return await _generate_complete(req)


async def _generate_complete(req: SVAGenerateRequest) -> dict:
    """Non-streaming generation with full validation pipeline."""

    # Step 1: Retrieve few-shot examples from RAG
    sources, few_shot_context = await _retrieve_few_shot_examples(req)

    # Step 2: Build prompt
    messages = _build_sva_prompt(req, few_shot_context)

    # Step 3: Generate via LLM
    logger.info(f"Generating SVA: '{req.description[:60]}...' mode={req.mode}")
    full_response = await ollama_service.chat(
        messages=messages,
        model=req.model,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
    )

    # Step 4: Extract code
    sva_code = extract_sva_code(full_response)

    if not sva_code:
        return SVAGenerateResponse(
            sva_code="",
            full_response=full_response,
            validation={"valid": False, "errors": ["No SystemVerilog code block found in response"]},
            sva2sby_compatible=False,
            sources=[_source_to_dict(s) for s in sources],
        ).model_dump()

    # Step 5: Validate
    if req.mode == "formal":
        result = validate_sva_for_formal(sva_code)
    else:
        result = validate_sv(sva_code)

    # Step 6: Auto-retry if validation failed and retry is enabled
    retried = False
    retry_reason = None

    if req.auto_retry and (not result.valid or not result.sva2sby_compatible):
        retry_reason = _summarize_issues(result)
        logger.info(f"Auto-retrying: {retry_reason}")

        retry_prompt = build_retry_prompt(req.description, sva_code, result)
        retry_messages = _build_retry_messages(req, retry_prompt)

        retry_response = await ollama_service.chat(
            messages=retry_messages,
            model=req.model,
            temperature=max(req.temperature - 0.1, 0.0),  # slightly lower temp for fix
            max_tokens=req.max_tokens,
        )

        retry_code = extract_sva_code(retry_response)
        if retry_code:
            # Re-validate the retry
            if req.mode == "formal":
                retry_result = validate_sva_for_formal(retry_code)
            else:
                retry_result = validate_sv(retry_code)

            # Use retry if it's better (fewer errors)
            if len(retry_result.errors) < len(result.errors) or (
                retry_result.sva2sby_compatible and not result.sva2sby_compatible
            ):
                sva_code = retry_code
                full_response = retry_response
                result = retry_result
                retried = True
                logger.info("Retry improved the result")
            else:
                logger.info("Retry did not improve — keeping original")

    # Step 7: Build response
    return SVAGenerateResponse(
        sva_code=sva_code,
        full_response=full_response,
        validation=build_validation_payload(result, sva_code),
        sva2sby_compatible=result.sva2sby_compatible,
        sources=[_source_to_dict(s) for s in sources],
        retried=retried,
        retry_reason=retry_reason,
    ).model_dump()


async def _generate_streaming(req: SVAGenerateRequest):
    """
    Streaming generation — sends tokens as SSE, then validation result at the end.
    Same SSE format as /api/chat for frontend compatibility.
    """
    sources, few_shot_context = await _retrieve_few_shot_examples(req)
    messages = _build_sva_prompt(req, few_shot_context)

    async def event_stream():
        full_response = ""

        # Stream tokens
        async for token in ollama_service.chat_stream(
            messages=messages,
            model=req.model,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        ):
            full_response += token
            data = json.dumps({"token": token, "done": False, "sources": None, "validation": None})
            yield f"data: {data}\n\n"

        # Validate after stream completes
        sva_code = extract_sva_code(full_response)
        if sva_code:
            if req.mode == "formal":
                result = validate_sva_for_formal(sva_code)
            else:
                result = validate_sv(sva_code)

            validation = build_validation_payload(result, sva_code)
        else:
            validation = {
                "valid": False,
                "errors": ["No code block found"],
                "warnings": [],
                "sva2sby_compatible": False,
                "banned_constructs": [],
                "diagnostics": [],
                "numbered_lines": [],
                "stats": {},
            }

        # Final event with sources + validation
        final = json.dumps({
            "token": "",
            "done": True,
            "sources": [_source_to_dict(s) for s in sources],
            "validation": validation,
        })
        yield f"data: {final}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ═══════════════════════════════════════════════════════════════
# RAG FEW-SHOT RETRIEVAL
# ═══════════════════════════════════════════════════════════════

async def _retrieve_few_shot_examples(req: SVAGenerateRequest) -> tuple[list, str]:
    """
    Retrieve relevant SVA patterns from ChromaDB as few-shot examples.
    Filters by protocol if specified.
    """
    # Build search query from description + protocol
    search_query = req.description
    if req.protocol:
        search_query = f"{req.protocol} {search_query}"

    # Filter metadata for protocol-specific patterns
    filter_metadata = None
    if req.protocol:
        filter_metadata = {"protocol": req.protocol.lower()}

    # Search sva_patterns and tool_docs collections
    collections = ["sva_patterns", "tool_docs"]

    try:
        results = await rag_service.retrieve(
            query=search_query,
            top_k=3,  # 3 few-shot examples is enough
            collections=collections,
            filter_metadata=filter_metadata,
        )
    except Exception as e:
        logger.warning(f"RAG retrieval failed: {e}")
        results = []

    if not results:
        # Retry without protocol filter
        try:
            results = await rag_service.retrieve(
                query=search_query,
                top_k=3,
                collections=collections,
            )
        except Exception:
            results = []

    # Build few-shot context string
    if results:
        parts = []
        for i, r in enumerate(results, 1):
            parts.append(f"--- Example {i} (from {r['source']}) ---\n{r['text']}")
        few_shot = "\n\n".join(parts)
    else:
        few_shot = ""

    return results, few_shot


# ═══════════════════════════════════════════════════════════════
# PROMPT BUILDING
# ═══════════════════════════════════════════════════════════════

def _build_sva_prompt(req: SVAGenerateRequest, few_shot_context: str) -> list[dict]:
    """Build the full message list for SVA generation."""
    system_prompt = get_system_prompt(req.mode, rag_active=bool(few_shot_context))

    # Add signal and configuration context
    config_block = f"""
CONFIGURATION:
- Clock: {req.clock}
- Reset: {req.reset} (active low)
- DUT module: {req.dut_module or '(not specified)'}
- Protocol: {req.protocol or '(not specified)'}
- DUT signals: {', '.join(req.dut_signals) if req.dut_signals else '(infer from description)'}
"""

    # Add few-shot examples
    if few_shot_context:
        examples_block = f"""
REFERENCE SVA PATTERNS (use these as templates for correct syntax):

{few_shot_context}

Use the patterns above as templates. Match the exact SVA construct syntax shown.
"""
    else:
        examples_block = ""

    # Build messages
    messages = [
        {"role": "system", "content": system_prompt + config_block + examples_block},
        {"role": "user", "content": req.description},
    ]

    return messages


def _build_retry_messages(req: SVAGenerateRequest, retry_prompt: str) -> list[dict]:
    """Build messages for retry attempt."""
    system_prompt = get_system_prompt(req.mode, rag_active=False)
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": retry_prompt},
    ]


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _source_to_dict(source: dict) -> dict:
    """Convert RAG result to a clean source dict for the response."""
    return {
        "source": source.get("source", ""),
        "section": source.get("section", ""),
        "score": source.get("score", 0),
        "collection": source.get("collection", ""),
    }


def _summarize_issues(result: ValidationResult) -> str:
    """Summarize validation issues for logging."""
    parts = []
    if result.errors:
        parts.append(f"{len(result.errors)} errors")
    if result.banned_constructs:
        parts.append(f"{len(result.banned_constructs)} banned constructs")
    if result.warnings:
        parts.append(f"{len(result.warnings)} warnings")
    return ", ".join(parts) if parts else "unknown issues"


# ═══════════════════════════════════════════════════════════════
# POST /api/sva/validate — Validate existing SVA code
# ═══════════════════════════════════════════════════════════════

class SVAValidateRequest(BaseModel):
    code: str
    mode: str = "formal"  # "formal" for strict, "sva" for general


@router.post("/validate")
async def validate_sva(req: SVAValidateRequest):
    """
    Validate existing SVA code without generating.
    Useful for checking hand-written or pasted SVA.
    """
    if req.mode == "formal":
        result = validate_sva_for_formal(req.code)
    else:
        result = validate_sv(req.code)

    return build_validation_payload(result, req.code)
