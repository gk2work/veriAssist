"""
VeriAssist v2.0 — Formal Verification Service

Orchestrates the complete formal verification pipeline:
  1. (Optional) Generate SVA from English via LLM
  2. Parse SVA into structured representation
  3. Lower SVA to synthesizable RTL with immediate assertions
  4. Stage SymbiYosys project (DUT + monitor + .sby config)
  5. Execute SymbiYosys as subprocess
  6. Parse results (PASS/FAIL/TIMEOUT/ERROR)
  7. Extract counterexample VCD on FAIL

Supports both synchronous (blocking) and async (job-based) execution.
"""

import os
import uuid
import time
import asyncio
import subprocess
import logging
import shutil
import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime

from app.services.sva_parser import parse_sva, format_parsed_summary
from app.services.sva_lowering import SVALoweringEngine
from app.services.sby_generator import (
    SbyConfig, SbyProject, SbyResult,
    generate_sby_project, quick_generate, quick_generate_standalone,
    generate_standalone_project_from_monitor,
    generate_raw_sby_project,
    parse_sby_output,
)

logger = logging.getLogger("veriassist.formal")

FORMAL_WORK_DIR = Path(__file__).parent.parent.parent / "data" / "formal_work"


# ═══════════════════════════════════════════════════════════════
# JOB TRACKING
# ═══════════════════════════════════════════════════════════════

@dataclass
class FormalJob:
    """Tracks the state of a formal verification job."""
    job_id: str
    status: str = "queued"     # queued | generating_sva | lowering | proving | complete | failed
    created_at: str = ""
    completed_at: str = ""

    # Input
    description: str = ""
    sva_code: str = ""
    dut_code: str = ""
    dut_filename: str = ""
    mode: str = "bmc"
    depth: int = 20
    solver: str = ""

    # Pipeline outputs
    lowered_rtl: str = ""
    sby_project_dir: str = ""
    parse_summary: str = ""

    # Result
    result: Optional[SbyResult] = None
    error_message: str = ""

    # Timing
    generation_time: float = 0
    lowering_time: float = 0
    proving_time: float = 0
    total_time: float = 0


# In-memory job store (sufficient for single-user local tool)
_jobs: dict[str, FormalJob] = {}


def get_job(job_id: str) -> Optional[FormalJob]:
    """Retrieve a job by ID."""
    return _jobs.get(job_id)


def list_jobs(limit: int = 20) -> list[FormalJob]:
    """List recent jobs, newest first."""
    jobs = sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)
    return jobs[:limit]


# ═══════════════════════════════════════════════════════════════
# SYNCHRONOUS PIPELINE (blocking, for direct API calls)
# ═══════════════════════════════════════════════════════════════

class FormalService:
    """Main formal verification service."""

    def __init__(self):
        self.lowering_engine = SVALoweringEngine()
        self._check_tools()

    def _check_tools(self):
        """Check if sby and yosys are available."""
        self.sby_available = shutil.which("sby") is not None
        self.yosys_available = shutil.which("yosys") is not None
        if self.sby_available:
            logger.info("SymbiYosys (sby) found in PATH")
        else:
            logger.warning("SymbiYosys (sby) NOT found. Formal verification unavailable.")
            logger.warning("Install OSS CAD Suite: https://github.com/YosysHQ/oss-cad-suite-build/releases")

    def is_available(self) -> bool:
        """Check if formal verification tools are installed."""
        return self.sby_available and self.yosys_available

    # ── Full Pipeline (SVA code → formal result) ──────────

    def run_formal(
        self,
        sva_code: str,
        dut_code: str = "",
        dut_filename: str = "dut.sv",
        dut_top: str = "",
        mode: str = "bmc",
        depth: int = 20,
        solver: str = "",
        timeout: int = 300,
        project_name: str = "",
    ) -> FormalJob:
        """
        Run the complete formal verification pipeline synchronously.

        Args:
            sva_code: SVA checker module code (from LLM or user)
            dut_code: DUT SystemVerilog code (optional for standalone)
            dut_filename: filename for the DUT
            dut_top: top module name in DUT
            mode: "bmc" | "prove" | "cover"
            depth: BMC depth (number of cycles)
            solver: SMT solver ("yices", "z3", "boolector", or "" for default)
            timeout: max seconds for sby execution
            project_name: custom name for the project directory

        Returns:
            FormalJob with complete results
        """
        if not project_name:
            project_name = f"formal_{uuid.uuid4().hex[:8]}"

        job = FormalJob(
            job_id=project_name,
            created_at=datetime.now().isoformat(),
            sva_code=sva_code,
            dut_code=dut_code,
            dut_filename=dut_filename,
            mode=mode,
            depth=depth,
            solver=solver,
        )
        _jobs[job.job_id] = job

        t_total = time.time()

        try:
            # Step 1: Parse SVA
            job.status = "lowering"
            t0 = time.time()

            parsed = parse_sva(sva_code)
            job.parse_summary = format_parsed_summary(parsed)
            logger.info(f"[{job.job_id}] Parsed SVA: {len(parsed.properties)} properties, {len(parsed.assertions)} assertions")

            # Step 2: Lower SVA to RTL
            lowered = self.lowering_engine.lower(parsed)
            job.lowered_rtl = lowered
            job.lowering_time = time.time() - t0
            logger.info(f"[{job.job_id}] Lowered to {len(lowered.splitlines())} lines of RTL ({job.lowering_time:.2f}s)")

            # Step 4: Run SymbiYosys
            if not self.is_available():
                job.status = "failed"
                job.error_message = "SymbiYosys (sby) not found in PATH. Install OSS CAD Suite."
                return job

            job.status = "proving"
            t0 = time.time()

            lowered_assert_labels = self._extract_lowered_assert_labels(lowered)
            if len(lowered_assert_labels) > 1:
                logger.info(
                    f"[{job.job_id}] Running {len(lowered_assert_labels)} assertions in isolated mode"
                )
                sby_result = self._run_isolated_assertions(
                    project_name=project_name,
                    parsed_module=parsed.module_name,
                    lowered_rtl=lowered,
                    assert_labels=lowered_assert_labels,
                    dut_code=dut_code,
                    dut_filename=dut_filename,
                    dut_top=dut_top,
                    mode=mode,
                    depth=depth,
                    solver=solver,
                    timeout=timeout,
                )
                job.sby_project_dir = str(FORMAL_WORK_DIR / project_name)
            else:
                # Stage SymbiYosys project
                if dut_code:
                    project = quick_generate(
                        sva_code=sva_code,
                        dut_code=dut_code,
                        dut_filename=dut_filename,
                        dut_top=dut_top,
                        mode=mode,
                        depth=depth,
                        solver=solver,
                        project_name=project_name,
                    )
                else:
                    project = quick_generate_standalone(
                        sva_code=sva_code,
                        mode=mode,
                        depth=depth,
                        solver=solver,
                        project_name=project_name,
                    )

                job.sby_project_dir = project.work_dir
                logger.info(f"[{job.job_id}] Staged sby project: {project.work_dir}")
                sby_result = self._run_sby(project.sby_file, project.work_dir, timeout)

            job.result = sby_result
            job.proving_time = time.time() - t0

            logger.info(
                f"[{job.job_id}] SymbiYosys result: {sby_result.status} "
                f"(depth={sby_result.depth_reached}, {job.proving_time:.2f}s)"
            )

            if sby_result.assertion_results:
                passed = [a for a in sby_result.assertion_results if a["status"] == "PASS"]
                failed = [a for a in sby_result.assertion_results if a["status"] == "FAIL"]
                skipped = [a for a in sby_result.assertion_results if a["status"] == "SKIPPED"]
                errored = [a for a in sby_result.assertion_results if a["status"] == "ERROR"]

                logger.info(
                    f"[{job.job_id}] Assertion summary: "
                    f"PASS={len(passed)} FAIL={len(failed)} "
                    f"SKIPPED={len(skipped)} ERROR={len(errored)}"
                )

                for assertion in passed:
                    logger.info(f"[{job.job_id}]   PASS: {assertion['name']}")
                for assertion in failed:
                    step_suffix = f" at step {assertion['step']}" if assertion.get("step") else ""
                    logger.info(f"[{job.job_id}]   FAIL: {assertion['name']}{step_suffix}")
                for assertion in skipped:
                    logger.info(f"[{job.job_id}]   SKIPPED: {assertion['name']}")
                for assertion in errored:
                    logger.info(f"[{job.job_id}]   ERROR: {assertion['name']} {assertion.get('message', '').strip()}".rstrip())
            elif sby_result.failed_assertions:
                for fa in sby_result.failed_assertions:
                    logger.info(f"[{job.job_id}]   FAIL: {fa['name']} at step {fa['step']}")

            if sby_result.status == "ERROR" and sby_result.error_message:
                first_error = sby_result.error_message.strip().splitlines()[-1]
                logger.error(f"[{job.job_id}] Formal run error detail: {first_error}")

            job.status = "complete"

        except Exception as e:
            logger.error(f"[{job.job_id}] Formal pipeline error: {e}", exc_info=True)
            job.status = "failed"
            job.error_message = str(e)

        job.total_time = time.time() - t_total
        job.completed_at = datetime.now().isoformat()

        return job

    # ── SymbiYosys Execution ──────────────────────────────

    def _run_sby(self, sby_file: str, work_dir: str, timeout: int = 300) -> SbyResult:
        """Execute SymbiYosys and parse its output."""
        try:
            proc = subprocess.run(
                ["sby", "-f", sby_file],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=os.path.dirname(sby_file),
            )

            return parse_sby_output(
                stdout=proc.stdout,
                stderr=proc.stderr,
                returncode=proc.returncode,
                work_dir=work_dir,
            )

        except subprocess.TimeoutExpired:
            logger.warning(f"SymbiYosys timed out after {timeout}s")
            return SbyResult(
                status="TIMEOUT",
                return_code=-1,
                error_message=f"Solver timed out after {timeout} seconds. Try reducing BMC depth.",
            )

        except FileNotFoundError:
            logger.error("sby executable not found")
            return SbyResult(
                status="ERROR",
                return_code=-1,
                error_message="SymbiYosys (sby) not found. Is OSS CAD Suite in PATH?",
            )

        except Exception as e:
            logger.error(f"SymbiYosys execution error: {e}")
            return SbyResult(
                status="ERROR",
                return_code=-1,
                error_message=str(e),
            )

    def _run_isolated_assertions(
        self,
        project_name: str,
        parsed_module: str,
        lowered_rtl: str,
        assert_labels: list[str],
        dut_code: str,
        dut_filename: str,
        dut_top: str,
        mode: str,
        depth: int,
        solver: str,
        timeout: int,
    ) -> SbyResult:
        """
        Run each lowered assertion in its own project so one failure does not
        cause the remaining assertions to be reported as skipped.
        """
        aggregate = SbyResult(status="PASS")
        combined_logs = []
        actual_dut_top = (dut_top or self._extract_module_name(dut_code)) if dut_code else ""
        parent_dir = FORMAL_WORK_DIR / project_name
        assertions_dir = parent_dir / "assertions"

        if parent_dir.exists():
            shutil.rmtree(parent_dir)
        assertions_dir.mkdir(parents=True, exist_ok=True)

        aggregate.log_paths["job_dir"] = str(parent_dir)
        aggregate.log_paths["assertions_dir"] = str(assertions_dir)

        for index, label in enumerate(assert_labels, start=1):
            isolated_monitor = self._disable_other_assertions(lowered_rtl, label)
            run_name = f"{project_name}__{index:02d}_{label}"[:96]
            run_dir = assertions_dir / run_name

            if dut_code:
                config = SbyConfig(
                    project_name=run_name,
                    mode=mode,
                    depth=depth,
                    engine="smtbmc",
                    solver=solver,
                    top_module=actual_dut_top,
                    monitor_module=parsed_module,
                )
                project = generate_sby_project(
                    config=config,
                    dut_contents={dut_filename: dut_code},
                    monitor_content=isolated_monitor,
                    work_dir=str(run_dir),
                )
            else:
                project = generate_standalone_project_from_monitor(
                    monitor_rtl=isolated_monitor,
                    top_module=parsed_module,
                    mode=mode,
                    depth=depth,
                    solver=solver,
                    project_name=run_name,
                    work_dir=str(run_dir),
                )

            logger.info(f"[{project_name}] Staged isolated run for {label}: {project.work_dir}")
            run_result = self._run_sby(project.sby_file, project.work_dir, timeout)

            selected = next(
                (a for a in run_result.assertion_results if a["name"] == label),
                None,
            )
            if not selected:
                selected = {
                    "name": label,
                    "status": run_result.status if run_result.status in {"PASS", "FAIL", "ERROR", "TIMEOUT"} else "ERROR",
                    "type": "ASSERT",
                    "location": "",
                    "file": "",
                    "line": 0,
                    "step": 0,
                    "message": run_result.error_message,
                    "tracefile": "",
                }

            selected["project_dir"] = project.work_dir
            selected["counterexample_vcd"] = run_result.counterexample_vcd
            selected["log_paths"] = run_result.log_paths
            aggregate.assertion_results.append(selected)

            if selected["status"] == "FAIL":
                aggregate.failed_assertions.append({
                    "name": selected["name"],
                    "file": selected.get("file", ""),
                    "line": selected.get("line", 0),
                    "step": selected.get("step", 0),
                    "message": selected.get("message", ""),
                })
                if not aggregate.counterexample_vcd:
                    aggregate.counterexample_vcd = run_result.counterexample_vcd
            elif selected["status"] in {"ERROR", "TIMEOUT"} and aggregate.status == "PASS":
                aggregate.status = selected["status"]

            if run_result.status == "FAIL":
                aggregate.status = "FAIL"

            aggregate.depth_reached = max(aggregate.depth_reached, run_result.depth_reached)
            aggregate.elapsed_seconds += run_result.elapsed_seconds

            if run_result.engine_output:
                combined_logs.append(f"=== {label} ===\n{run_result.engine_output}")
            if run_result.error_message:
                aggregate.error_message += (
                    ("\n" if aggregate.error_message else "")
                    + f"{label}: {run_result.error_message.strip()}"
                )

        aggregate.engine_output = "\n\n".join(combined_logs)
        return aggregate

    def _extract_lowered_assert_labels(self, lowered_rtl: str) -> list[str]:
        """Return the labels of actual lowered assert statements."""
        return re.findall(r'^\s*(\w+):\s*assert\s*\(', lowered_rtl, re.MULTILINE)

    def _disable_other_assertions(self, lowered_rtl: str, active_label: str) -> str:
        """Disable all lowered assert statements except the selected one."""
        lines = []
        pattern = re.compile(r'^(\s*)(\w+):\s*assert\s*\(')
        for line in lowered_rtl.splitlines():
            m = pattern.match(line)
            if m and m.group(2) != active_label:
                indent = m.group(1)
                label = m.group(2)
                lines.append(f"{indent}begin end // disabled assertion {label}")
            else:
                lines.append(line)
        return "\n".join(lines)

    def _extract_module_name(self, dut_code: str) -> str:
        """Best-effort extraction of DUT top module name."""
        if not dut_code:
            return ""
        m = re.search(r'module\s+(\w+)', dut_code)
        return m.group(1) if m else ""

    # ── Lower Only (no sby execution) ─────────────────────

    def lower_only(self, sva_code: str) -> dict:
        """
        Just parse and lower SVA without running formal.
        Returns the lowered RTL for inspection.
        """
        parsed = parse_sva(sva_code)
        lowered = self.lowering_engine.lower(parsed)
        return {
            "parsed_summary": format_parsed_summary(parsed),
            "lowered_rtl": lowered,
            "properties": len(parsed.properties),
            "assertions": len(parsed.assertions),
        }

    # ── Health Check ──────────────────────────────────────

    def health(self) -> dict:
        """Check formal verification subsystem health."""
        return {
            "sby": "available" if self.sby_available else "not_installed",
            "yosys": "available" if self.yosys_available else "not_installed",
            "sby_path": shutil.which("sby") or "",
            "yosys_path": shutil.which("yosys") or "",
            "work_dir": str(FORMAL_WORK_DIR),
            "active_jobs": sum(1 for j in _jobs.values() if j.status in ("queued", "lowering", "proving")),
            "total_jobs": len(_jobs),
        }


# ═══════════════════════════════════════════════════════════════
# DIRECT FILE PIPELINE (bypasses SVA lowering; for file uploads)
# ═══════════════════════════════════════════════════════════════

def run_formal_direct(
    design_file_contents: dict[str, str],
    sva_file_contents: dict[str, str],
    mode: str = "bmc",
    depth: int = 20,
    solver: str = "",
    top_module: str = "",
    timeout: int = 300,
    project_name: str = "",
) -> FormalJob:
    """
    Run formal verification directly on uploaded files, skipping the SVA
    lowering engine.  Suitable for native SVA with bind statements.
    """
    if not project_name:
        project_name = f"fv_{uuid.uuid4().hex[:8]}"

    job = FormalJob(
        job_id=project_name,
        created_at=datetime.now().isoformat(),
        dut_code="\n\n".join(design_file_contents.values()),
        sva_code="\n\n".join(sva_file_contents.values()),
        dut_filename=next(iter(design_file_contents), "dut.sv"),
        mode=mode,
        depth=depth,
        solver=solver,
        status="proving",
    )
    _jobs[project_name] = job

    t0 = time.time()
    try:
        project = generate_raw_sby_project(
            design_file_contents=design_file_contents,
            sva_file_contents=sva_file_contents,
            mode=mode,
            depth=depth,
            solver=solver,
            top_module=top_module,
            timeout=timeout,
            project_name=project_name,
        )
        job.sby_project_dir = project.work_dir
        sby_result = formal_service._run_sby(project.sby_file, project.work_dir, timeout)
        job.result = sby_result
        job.proving_time = time.time() - t0
        job.status = "complete"
    except Exception as e:
        logger.error(f"[{project_name}] Direct formal error: {e}", exc_info=True)
        job.status = "failed"
        job.error_message = str(e)

    job.total_time = time.time() - t0
    job.completed_at = datetime.now().isoformat()
    return job


async def run_formal_direct_async(
    design_file_contents: dict[str, str],
    sva_file_contents: dict[str, str],
    mode: str = "bmc",
    depth: int = 20,
    solver: str = "",
    top_module: str = "",
    timeout: int = 300,
    project_name: str = "",
) -> FormalJob:
    """Async wrapper around run_formal_direct — returns job immediately."""
    if not project_name:
        project_name = f"fv_{uuid.uuid4().hex[:8]}"

    job = FormalJob(
        job_id=project_name,
        created_at=datetime.now().isoformat(),
        dut_code="\n\n".join(design_file_contents.values()),
        sva_code="\n\n".join(sva_file_contents.values()),
        dut_filename=next(iter(design_file_contents), "dut.sv"),
        mode=mode,
        depth=depth,
        solver=solver,
        status="queued",
    )
    _jobs[project_name] = job

    loop = asyncio.get_event_loop()
    loop.run_in_executor(
        None,
        lambda: run_formal_direct(
            design_file_contents=design_file_contents,
            sva_file_contents=sva_file_contents,
            mode=mode,
            depth=depth,
            solver=solver,
            top_module=top_module,
            timeout=timeout,
            project_name=project_name,
        ),
    )
    return job


# ═══════════════════════════════════════════════════════════════
# ASYNC PIPELINE (for background execution from API)
# ═══════════════════════════════════════════════════════════════

async def run_formal_async(
    sva_code: str,
    dut_code: str = "",
    dut_filename: str = "dut.sv",
    dut_top: str = "",
    mode: str = "bmc",
    depth: int = 20,
    solver: str = "",
    timeout: int = 300,
    project_name: str = "",
) -> FormalJob:
    """
    Run formal verification in a background thread (non-blocking).
    Returns the job immediately; poll status via get_job().
    """
    job_id = project_name or f"formal_{uuid.uuid4().hex[:8]}"

    # Create job entry immediately
    job = FormalJob(
        job_id=job_id,
        status="queued",
        created_at=datetime.now().isoformat(),
        sva_code=sva_code,
        dut_code=dut_code,
        dut_filename=dut_filename,
        mode=mode,
        depth=depth,
        solver=solver,
    )
    _jobs[job_id] = job

    # Run in thread pool to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: _run_formal_sync(job, timeout),
    )

    return job


def _run_formal_sync(job: FormalJob, timeout: int):
    """Synchronous formal execution (called from thread pool)."""
    service = formal_service
    result_job = service.run_formal(
        sva_code=job.sva_code,
        dut_code=job.dut_code,
        dut_filename=job.dut_filename,
        mode=job.mode,
        depth=job.depth,
        solver=job.solver,
        timeout=timeout,
        project_name=job.job_id,
    )

    # Update the tracked job in-place
    job.status = result_job.status
    job.result = result_job.result
    job.lowered_rtl = result_job.lowered_rtl
    job.parse_summary = result_job.parse_summary
    job.sby_project_dir = result_job.sby_project_dir
    job.lowering_time = result_job.lowering_time
    job.proving_time = result_job.proving_time
    job.total_time = result_job.total_time
    job.error_message = result_job.error_message
    job.completed_at = result_job.completed_at


# ═══════════════════════════════════════════════════════════════
# COUNTEREXAMPLE READING
# ═══════════════════════════════════════════════════════════════

def read_counterexample_vcd(vcd_path: str, max_signals: int = 64) -> dict:
    """
    Read a counterexample VCD file and extract waveform-friendly signal data.
    Returns a compact representation that is still usable by the debug assistant.
    """
    if not os.path.exists(vcd_path):
        return {"error": f"VCD file not found: {vcd_path}"}

    try:
        lines = Path(vcd_path).read_text(encoding="utf-8", errors="replace").splitlines()

        var_map: dict[str, dict] = {}
        transitions: list[dict] = []
        timepoints: list[int] = []
        current_time = 0
        definitions_complete = False
        scope_stack: list[str] = []
        timescale = ""

        def normalize_value(raw_value: str) -> str:
            value = raw_value.strip()
            return value.lower() if value else "x"

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if not definitions_complete and line.startswith("$timescale"):
                timescale = line.replace("$timescale", "").replace("$end", "").strip()
                continue

            if not definitions_complete and line.startswith("$scope"):
                parts = line.split()
                if len(parts) >= 3:
                    scope_stack.append(parts[2])
                continue

            if not definitions_complete and line.startswith("$upscope"):
                if scope_stack:
                    scope_stack.pop()
                continue

            if line.startswith("$var"):
                parts = line.split()
                if len(parts) >= 6:
                    var_type = parts[1]
                    try:
                        width = int(parts[2])
                    except ValueError:
                        width = 1
                    symbol = parts[3]
                    name = " ".join(parts[4:-1])
                    full_name = ".".join([*scope_stack, name]) if scope_stack else name
                    scope = ".".join(scope_stack)
                    var_map[symbol] = {
                        "name": name,
                        "full_name": full_name,
                        "scope": scope,
                        "width": width,
                        "type": var_type,
                    }
                continue

            if line.startswith("$enddefinitions"):
                definitions_complete = True
                continue

            if not definitions_complete:
                continue

            if line.startswith("#"):
                try:
                    current_time = int(line[1:])
                    if not timepoints or timepoints[-1] != current_time:
                        timepoints.append(current_time)
                except ValueError:
                    continue
                continue

            if line.startswith("$"):
                continue

            value = ""
            symbol = ""
            if line[0] in "01xXzZuUwWlLhH-":
                value = normalize_value(line[0])
                symbol = line[1:].strip()
            elif line[0] in "bBrR":
                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    value = normalize_value(parts[0][1:])
                    symbol = parts[1].strip()

            if not symbol or symbol not in var_map:
                continue

            sig = var_map[symbol]
            transitions.append({
                "time": current_time,
                "signal": sig["full_name"],
                "name": sig["name"],
                "value": value,
                "width": sig["width"],
                "type": sig["type"],
            })

        signal_defs = sorted(var_map.values(), key=lambda item: item["full_name"])
        selected_defs = signal_defs[:max_signals]
        selected_names = {sig["full_name"] for sig in selected_defs}
        selected_transitions = [
            transition for transition in transitions
            if transition["signal"] in selected_names
        ]

        timeline = {
            sig["full_name"]: [
                transition
                for transition in selected_transitions
                if transition["signal"] == sig["full_name"]
            ]
            for sig in selected_defs
        }

        signal_details = []
        for sig in selected_defs:
            sig_timeline = timeline[sig["full_name"]]
            initial_value = sig_timeline[0]["value"] if sig_timeline else "x"
            final_value = sig_timeline[-1]["value"] if sig_timeline else initial_value
            signal_details.append({
                "name": sig["name"],
                "full_name": sig["full_name"],
                "scope": sig["scope"],
                "width": sig["width"],
                "type": sig["type"],
                "initial_value": initial_value,
                "final_value": final_value,
                "transitions": sig_timeline[:500],
            })
        max_time = max(timepoints, default=0)

        return {
            "path": vcd_path,
            "timescale": timescale or "1ns",
            "signals": [sig["full_name"] for sig in selected_defs],
            "signal_details": signal_details,
            "total_cycles": max_time,
            "timepoints": timepoints[:1000],
            "start_time": timepoints[0] if timepoints else 0,
            "end_time": max_time,
            "transitions": selected_transitions[:1000],
            "timeline": timeline,
            "signal_count": len(selected_defs),
        }

    except Exception as e:
        logger.error(f"Failed to parse VCD: {e}")
        return {"error": str(e)}


def format_counterexample_for_llm(vcd_data: dict, max_cycles: int = 30) -> str:
    """
    Format counterexample data into a text summary suitable for
    the LLM debug assistant to analyze.
    """
    if "error" in vcd_data:
        return f"VCD parsing error: {vcd_data['error']}"

    lines = []
    lines.append(f"COUNTEREXAMPLE TRACE ({vcd_data.get('total_cycles', '?')} cycles, {vcd_data.get('signal_count', '?')} signals)")
    lines.append("")

    # Build cycle-by-cycle state
    timeline = vcd_data.get("timeline", {})
    signals = vcd_data.get("signals", [])

    if not signals:
        return "No signal data in counterexample."

    # Track current values
    current_values = {sig: "x" for sig in signals}

    # Collect all unique timestamps
    all_times = sorted(set(t["time"] for t in vcd_data.get("transitions", [])))
    all_times = [t for t in all_times if t <= max_cycles * 10]  # rough cycle limit

    for t in all_times:
        # Update values at this timestamp
        for trans in vcd_data.get("transitions", []):
            if trans["time"] == t:
                current_values[trans["signal"]] = trans["value"]

        # Format state
        state_parts = [f"{sig}={current_values[sig]}" for sig in signals[:10]]
        lines.append(f"  @{t}: {', '.join(state_parts)}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════

formal_service = FormalService()
