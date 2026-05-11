"""
VeriAssist v2.0 — Formal Verification Router

POST /api/formal/run              — Full pipeline: SVA → lower → prove (async)
POST /api/formal/run-sync         — Full pipeline synchronous (blocking)
POST /api/formal/lower            — Parse + lower SVA to RTL (no sby)
POST /api/formal/debug/{job_id}   — AI analysis of counterexample (Phase 5)
POST /api/formal/debug-quick      — Standalone debug analysis (no job needed)
POST /api/formal/rerun            — Re-run with modified code after fix
GET  /api/formal/status/{job_id}  — Poll job status
GET  /api/formal/jobs             — List recent formal jobs
GET  /api/formal/counterexample/{job_id} — Get VCD data
GET  /api/formal/lowered/{job_id} — Get lowered RTL
GET  /api/formal/health           — Formal subsystem health check
"""

import logging
import os
import uuid
from typing import Optional, List
from fastapi import APIRouter, BackgroundTasks, File, Form, Query, UploadFile
from pydantic import BaseModel, Field

from app.services.formal_service import (
    formal_service,
    run_formal_async,
    run_formal_direct_async,
    get_job,
    list_jobs,
    read_counterexample_vcd,
    format_counterexample_for_llm,
    FormalJob,
)
from app.services.debug_service import debug_service, quick_debug_analysis
from app.services.sv_validator import (
    build_validation_payload,
    get_numbered_lines,
    validate_sv,
)

logger = logging.getLogger("veriassist.formal_router")
router = APIRouter(prefix="/api/formal", tags=["formal"])


# ═══════════════════════════════════════════════════════════════
# REQUEST MODELS
# ═══════════════════════════════════════════════════════════════

class FormalRunRequest(BaseModel):
    sva_code: str
    dut_code: str = ""
    dut_filename: str = "dut.sv"
    dut_top: str = ""
    mode: str = "bmc"
    depth: int = 20
    solver: str = ""
    timeout: int = 300
    project_name: str = ""


class FormalLowerRequest(BaseModel):
    sva_code: str


class FormalValidateRTLRequest(BaseModel):
    code: str


class FormalDebugRequest(BaseModel):
    dut_code: str = ""
    model: Optional[str] = None
    temperature: float = 0.2


class QuickDebugRequest(BaseModel):
    sva_code: str
    dut_code: str = ""
    failed_assertion: str = "unknown"
    violation_step: int = -1
    vcd_summary: str = ""
    model: Optional[str] = None


class FormalRerunRequest(BaseModel):
    sva_code: str
    dut_code: str = ""
    dut_filename: str = "dut.sv"
    dut_top: str = ""
    mode: str = "bmc"
    depth: int = 20
    solver: str = ""
    timeout: int = 300
    previous_job_id: str = ""


# ═══════════════════════════════════════════════════════════════
# POST /api/formal/run — Async full pipeline
# ═══════════════════════════════════════════════════════════════

@router.post("/run")
async def run_formal(req: FormalRunRequest, background_tasks: BackgroundTasks):
    """
    Run the full formal verification pipeline asynchronously.
    Returns immediately with a job_id. Poll GET /api/formal/status/{job_id}.
    """
    if not formal_service.is_available():
        return {
            "error": "SymbiYosys not available",
            "message": "Install OSS CAD Suite and ensure 'sby' is in PATH.",
        }

    job = await run_formal_async(
        sva_code=req.sva_code,
        dut_code=req.dut_code,
        dut_filename=req.dut_filename,
        dut_top=req.dut_top,
        mode=req.mode,
        depth=req.depth,
        solver=req.solver,
        timeout=req.timeout,
        project_name=req.project_name,
    )

    return _job_to_response(job)


# ═══════════════════════════════════════════════════════════════
# POST /api/formal/run-sync — Synchronous full pipeline
# ═══════════════════════════════════════════════════════════════

@router.post("/run-sync")
async def run_formal_sync(req: FormalRunRequest):
    """Run the full formal pipeline synchronously. Returns complete results."""
    if not formal_service.is_available():
        return {
            "error": "SymbiYosys not available",
            "message": "Install OSS CAD Suite and ensure 'sby' is in PATH.",
        }

    job = formal_service.run_formal(
        sva_code=req.sva_code,
        dut_code=req.dut_code,
        dut_filename=req.dut_filename,
        dut_top=req.dut_top,
        mode=req.mode,
        depth=req.depth,
        solver=req.solver,
        timeout=req.timeout,
        project_name=req.project_name,
    )

    return _job_to_response(job)


# ═══════════════════════════════════════════════════════════════
# POST /api/formal/run-upload — File-upload based full pipeline
# ═══════════════════════════════════════════════════════════════

@router.post("/run-upload")
async def run_formal_upload(
    design_files: List[UploadFile] = File(...),
    sva_files: List[UploadFile] = File(default=[]),
    mode: str = Form("bmc"),
    depth: int = Form(20),
    solver: str = Form(""),
    timeout: int = Form(300),
    top_module: str = Form(""),
    project_name: str = Form(""),
):
    """
    Run formal verification from uploaded design and SVA files.
    Accepts multipart/form-data with design_files + sva_files.
    Returns immediately with a job_id. Poll GET /api/formal/status/{job_id}.
    """
    if not formal_service.is_available():
        return {
            "error": "SymbiYosys not available",
            "message": "Install OSS CAD Suite and ensure 'sby' is in PATH.",
        }

    # Read design files — skip blank placeholders sent by the frontend
    dut_parts: list[str] = []
    first_dut_filename = "dut.sv"
    for i, f in enumerate(design_files):
        raw = await f.read()
        text = raw.decode("utf-8", errors="replace").strip()
        name = (f.filename or "dut.sv").strip()
        if text and not name.startswith("_empty"):
            dut_parts.append(text)
            if i == 0:
                first_dut_filename = name

    # Read SVA files — skip blank placeholders
    sva_parts: list[str] = []
    for f in sva_files:
        raw = await f.read()
        text = raw.decode("utf-8", errors="replace").strip()
        name = (f.filename or "sva.sv").strip()
        if text and not name.startswith("_empty"):
            sva_parts.append(text)

    dut_code = "\n\n".join(dut_parts)
    sva_code = "\n\n".join(sva_parts)

    if not dut_code.strip() and not sva_code.strip():
        return {"error": "No file content provided. Upload at least one design or SVA file."}

    # Use the same pipeline as the text-based Formal tab:
    # SVA code → custom lowering engine → sby formal verification
    job = await run_formal_async(
        sva_code=sva_code,
        dut_code=dut_code,
        dut_filename=first_dut_filename,
        dut_top=top_module,
        mode=mode,
        depth=depth,
        solver=solver,
        timeout=timeout,
        project_name=project_name or f"fv_{uuid.uuid4().hex[:8]}",
    )

    return _job_to_response(job)


# ═══════════════════════════════════════════════════════════════
# POST /api/formal/lower — Parse + lower only
# ═══════════════════════════════════════════════════════════════

@router.post("/lower")
async def lower_sva(req: FormalLowerRequest):
    """Parse and lower SVA to synthesizable RTL without running formal."""
    try:
        result = formal_service.lower_only(req.sva_code)
        lowered_validation = build_validation_payload(
            validate_sv(result["lowered_rtl"]),
            result["lowered_rtl"],
        )
        return {
            "success": True,
            "lowered_rtl": result["lowered_rtl"],
            "lowered_rtl_validation": lowered_validation,
            "lowered_rtl_numbered_lines": lowered_validation["numbered_lines"],
            "parsed_summary": result["parsed_summary"],
            "properties": result["properties"],
            "assertions": result["assertions"],
        }
    except Exception as e:
        logger.error(f"Lowering failed: {e}", exc_info=True)
        return {"success": False, "error": str(e), "lowered_rtl": ""}


@router.post("/validate-rtl")
async def validate_lowered_rtl(req: FormalValidateRTLRequest):
    """Validate pasted or generated lowered RTL and return line-aware diagnostics."""
    result = validate_sv(req.code)
    return build_validation_payload(result, req.code)


# ═══════════════════════════════════════════════════════════════
# POST /api/formal/debug/{job_id} — AI counterexample analysis
# ═══════════════════════════════════════════════════════════════

@router.post("/debug/{job_id}")
async def debug_counterexample(job_id: str, req: FormalDebugRequest):
    """
    Analyze a failed formal job's counterexample using the LLM.

    The LLM receives the counterexample VCD trace, the SVA properties,
    the lowered RTL, and optionally the DUT code. It returns a structured
    analysis with: violation cycle, signal trace, root cause, classification
    (DESIGN_BUG/PROPERTY_ISSUE/CONSTRAINT_MISSING/RESET_ISSUE), suggested
    fix with corrected code, and follow-up property recommendations.

    Requires: The job must have status "complete" with result "FAIL".
    """
    job = get_job(job_id)
    if not job:
        return {"error": "Job not found", "job_id": job_id}

    if not job.result or job.result.status != "FAIL":
        return {
            "error": "Job did not fail — no counterexample to analyze",
            "job_id": job_id,
            "status": job.result.status if job.result else job.status,
        }

    analysis = await debug_service.analyze_counterexample(
        job_id=job_id,
        dut_code=req.dut_code or job.dut_code,
        model=req.model,
        temperature=req.temperature,
    )

    return {
        "job_id": job_id,
        "analysis": {
            "summary": analysis.summary,
            "violation_cycle": analysis.violation_cycle,
            "violation_assertion": analysis.violation_assertion,
            "violation_description": analysis.violation_description,
            "signal_trace": analysis.signal_trace,
            "root_cause": analysis.root_cause,
            "classification": analysis.classification,
            "suggested_fix": analysis.suggested_fix,
            "fixed_code": analysis.fixed_code,
            "followup_properties": analysis.followup_properties,
            "recommendations": analysis.recommendations,
            "model_used": analysis.model_used,
            "analysis_time": round(analysis.analysis_time, 2),
        },
        "raw_response": analysis.raw_response,
    }


# ═══════════════════════════════════════════════════════════════
# POST /api/formal/debug-quick — Standalone debug (no job needed)
# ═══════════════════════════════════════════════════════════════

@router.post("/debug-quick")
async def debug_quick(req: QuickDebugRequest):
    """
    Standalone counterexample analysis without a formal job.
    Useful for analyzing failures from external tools or pasted traces.
    """
    analysis = await quick_debug_analysis(
        sva_code=req.sva_code,
        dut_code=req.dut_code,
        failed_assertion=req.failed_assertion,
        violation_step=req.violation_step,
        vcd_summary=req.vcd_summary,
        model=req.model,
    )

    return {
        "analysis": {
            "summary": analysis.summary,
            "violation_cycle": analysis.violation_cycle,
            "violation_assertion": analysis.violation_assertion,
            "root_cause": analysis.root_cause,
            "classification": analysis.classification,
            "suggested_fix": analysis.suggested_fix,
            "fixed_code": analysis.fixed_code,
            "followup_properties": analysis.followup_properties,
        },
        "raw_response": analysis.raw_response,
    }


# ═══════════════════════════════════════════════════════════════
# POST /api/formal/rerun — Re-run with modified code after fix
# ═══════════════════════════════════════════════════════════════

@router.post("/rerun")
async def rerun_formal(req: FormalRerunRequest):
    """
    Re-run formal verification with modified SVA or DUT code after applying a fix.

    If previous_job_id is provided, the response includes a comparison
    with the previous run (same failure? new failure? fixed?).
    """
    if not formal_service.is_available():
        return {"error": "SymbiYosys not available"}

    # Run the new check
    job = formal_service.run_formal(
        sva_code=req.sva_code,
        dut_code=req.dut_code,
        dut_filename=req.dut_filename,
        dut_top=req.dut_top,
        mode=req.mode,
        depth=req.depth,
        solver=req.solver,
        timeout=req.timeout,
    )

    response = _job_to_response(job)

    # Compare with previous run if provided
    if req.previous_job_id:
        prev_job = get_job(req.previous_job_id)
        if prev_job and prev_job.result:
            prev_status = prev_job.result.status
            new_status = job.result.status if job.result else "ERROR"

            if prev_status == "FAIL" and new_status == "PASS":
                response["fix_verdict"] = "FIXED"
                response["fix_message"] = "The fix resolved the previous failure. All assertions now pass."
            elif prev_status == "FAIL" and new_status == "FAIL":
                # Check if same assertion failed
                prev_asserts = {fa["name"] for fa in prev_job.result.failed_assertions}
                new_asserts = {fa["name"] for fa in (job.result.failed_assertions if job.result else [])}
                if prev_asserts == new_asserts:
                    response["fix_verdict"] = "NOT_FIXED"
                    response["fix_message"] = "The same assertion(s) still fail. The fix was insufficient."
                else:
                    response["fix_verdict"] = "DIFFERENT_FAILURE"
                    response["fix_message"] = (
                        f"Different assertion(s) now fail. "
                        f"Previous: {prev_asserts}. Current: {new_asserts}. "
                        f"The fix may have introduced a regression."
                    )
            elif prev_status == "FAIL" and new_status == "ERROR":
                response["fix_verdict"] = "ERROR"
                response["fix_message"] = "The modified code has a compilation or elaboration error."
            else:
                response["fix_verdict"] = "UNKNOWN"
                response["fix_message"] = f"Previous: {prev_status}, Current: {new_status}"

            response["previous_job_id"] = req.previous_job_id
            response["previous_status"] = prev_status

    return response


# ═══════════════════════════════════════════════════════════════
# GET /api/formal/status/{job_id} — Poll job status
# ═══════════════════════════════════════════════════════════════

@router.get("/status/{job_id}")
async def get_formal_status(job_id: str):
    """Poll the status of a formal verification job."""
    job = get_job(job_id)
    if not job:
        return {"error": "Job not found", "job_id": job_id}
    return _job_to_response(job)


# ═══════════════════════════════════════════════════════════════
# GET /api/formal/jobs — List recent jobs
# ═══════════════════════════════════════════════════════════════

@router.get("/jobs")
async def list_formal_jobs(limit: int = 20):
    """List recent formal verification jobs."""
    jobs = list_jobs(limit)
    return {
        "count": len(jobs),
        "jobs": [
            {
                "job_id": j.job_id,
                "status": j.status,
                "mode": j.mode,
                "depth": j.depth,
                "result_status": j.result.status if j.result else None,
                "total_time": round(j.total_time, 2),
                "created_at": j.created_at,
            }
            for j in jobs
        ],
    }


# ═══════════════════════════════════════════════════════════════
# GET /api/formal/counterexample/{job_id}
# ═══════════════════════════════════════════════════════════════

@router.get("/counterexample/{job_id}")
async def get_counterexample(job_id: str, assertion: str = Query(default="")):
    """Get counterexample trace data for a failed formal job or a specific assertion."""
    job = get_job(job_id)
    if not job:
        return {"error": "Job not found"}

    if not job.result or job.result.status != "FAIL":
        return {"error": "No counterexample available (job did not FAIL)"}

    selected_assertion, vcd_path = _resolve_counterexample_trace(job, assertion)
    if not vcd_path:
        return {"error": "No VCD file found for this job"}

    vcd_data = read_counterexample_vcd(vcd_path)
    llm_summary = format_counterexample_for_llm(vcd_data)

    return {
        "job_id": job_id,
        "assertion": selected_assertion,
        "vcd_path": vcd_path,
        "vcd_data": vcd_data,
        "llm_summary": llm_summary,
        "failed_assertions": job.result.failed_assertions,
    }


# ═══════════════════════════════════════════════════════════════
# GET /api/formal/lowered/{job_id}
# ═══════════════════════════════════════════════════════════════

@router.get("/lowered/{job_id}")
async def get_lowered_rtl(job_id: str):
    """Get the lowered RTL for a formal job."""
    job = get_job(job_id)
    if not job:
        return {"error": "Job not found"}
    lowered_validation = build_validation_payload(validate_sv(job.lowered_rtl), job.lowered_rtl) if job.lowered_rtl else None
    return {
        "job_id": job_id,
        "lowered_rtl": job.lowered_rtl,
        "lowered_rtl_validation": lowered_validation,
        "lowered_rtl_numbered_lines": get_numbered_lines(job.lowered_rtl) if job.lowered_rtl else [],
        "parse_summary": job.parse_summary,
    }


# ═══════════════════════════════════════════════════════════════
# GET /api/formal/health
# ═══════════════════════════════════════════════════════════════

@router.get("/health")
async def formal_health():
    """Check formal verification subsystem health."""
    return formal_service.health()


# ═══════════════════════════════════════════════════════════════
# RESPONSE BUILDER
# ═══════════════════════════════════════════════════════════════

def _job_to_response(job: FormalJob) -> dict:
    """Convert a FormalJob to an API response dict."""
    response = {
        "job_id": job.job_id,
        "status": job.status,
        "mode": job.mode,
        "depth": job.depth,
        "solver": job.solver,
        "project_dir": job.sby_project_dir,
        "created_at": job.created_at,
        "completed_at": job.completed_at,
        "timing": {
            "lowering_seconds": round(job.lowering_time, 3),
            "proving_seconds": round(job.proving_time, 3),
            "total_seconds": round(job.total_time, 3),
        },
    }

    if job.status == "failed":
        response["error"] = job.error_message

    if job.result:
        r = job.result
        response["result"] = {
            "status": r.status,
            "depth_reached": r.depth_reached,
            "elapsed_seconds": round(r.elapsed_seconds, 3),
            "failed_assertions": r.failed_assertions,
            "assertions": r.assertion_results,
            "assertion_summary": {
                "total": len(r.assertion_results),
                "passed": sum(1 for a in r.assertion_results if a["status"] == "PASS"),
                "failed": sum(1 for a in r.assertion_results if a["status"] == "FAIL"),
                "skipped": sum(1 for a in r.assertion_results if a["status"] == "SKIPPED"),
                "errors": sum(1 for a in r.assertion_results if a["status"] == "ERROR"),
            },
            "has_counterexample": bool(r.counterexample_vcd),
            "counterexample_vcd": r.counterexample_vcd,
            "error_message": r.error_message,
            "log_paths": r.log_paths,
            "logs": {
                "stdout": r.engine_output,
                "stderr": r.stderr_output,
                "sby_log": r.detailed_logs.get("sby_log", ""),
                "engine_log": r.detailed_logs.get("engine_log", ""),
                "task_status": r.detailed_logs.get("task_status", ""),
                "status_path": r.detailed_logs.get("status_path", ""),
                "marker_name": r.detailed_logs.get("marker_name", ""),
                "marker_contents": r.detailed_logs.get("marker_contents", ""),
                "junit_xml": r.detailed_logs.get("junit_xml", ""),
            },
        }

        if r.engine_output:
            output_lines = r.engine_output.strip().split("\n")
            response["result"]["engine_summary"] = output_lines[-20:]
        elif r.detailed_logs.get("sby_log"):
            output_lines = r.detailed_logs["sby_log"].strip().split("\n")
            response["result"]["engine_summary"] = output_lines[-20:]

    if job.lowered_rtl:
        response["has_lowered_rtl"] = True
        response["lowered_rtl_lines"] = len(job.lowered_rtl.splitlines())
        response["lowered_rtl_numbered_lines"] = get_numbered_lines(job.lowered_rtl)
        response["lowered_rtl_validation"] = build_validation_payload(
            validate_sv(job.lowered_rtl),
            job.lowered_rtl,
        )

    if job.parse_summary:
        response["parse_summary"] = job.parse_summary

    return response


def _resolve_counterexample_trace(job: FormalJob, assertion_name: str = "") -> tuple[Optional[dict], str]:
    """Resolve the most relevant VCD path for a job or a specific assertion."""
    if not job.result:
        return None, ""

    target_name = (assertion_name or "").strip()
    assertion_results = job.result.assertion_results or []
    selected_assertion = None

    if target_name:
        selected_assertion = next(
            (assertion for assertion in assertion_results if assertion.get("name") == target_name),
            None,
        )
        if not selected_assertion:
            return None, ""

    candidates = []
    if selected_assertion:
        candidates.extend(_candidate_trace_paths(job, selected_assertion))
    else:
        if job.result.counterexample_vcd:
            candidates.append(job.result.counterexample_vcd)
        for assertion in assertion_results:
            assertion_candidates = _candidate_trace_paths(job, assertion)
            if not assertion_candidates:
                continue
            candidates.extend(assertion_candidates)
            selected_assertion = assertion
            if any(candidate and os.path.exists(candidate) for candidate in assertion_candidates):
                break

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return selected_assertion, candidate

    return selected_assertion, ""


def _candidate_trace_paths(job: FormalJob, assertion: dict) -> list[str]:
    """Build possible absolute trace paths from assertion metadata."""
    candidates: list[str] = []
    direct_path = (assertion.get("counterexample_vcd") or "").strip()
    if direct_path:
        candidates.append(direct_path)

    tracefile = (assertion.get("tracefile") or "").strip()
    if not tracefile:
        return candidates

    if os.path.isabs(tracefile):
        candidates.append(tracefile)
        return candidates

    base_dirs = [
        assertion.get("project_dir") or "",
        job.result.log_paths.get("task_dir", "") if job.result else "",
        job.sby_project_dir or "",
    ]
    for base_dir in base_dirs:
        if base_dir:
            candidates.append(os.path.join(base_dir, tracefile))

    return candidates
