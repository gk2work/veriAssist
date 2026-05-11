"""
VeriAssist v2.0 — Counterexample Debug Service

When SymbiYosys returns FAIL, this service:
  1. Reads the counterexample VCD trace
  2. Combines it with the original SVA, DUT code, and failed assertion info
  3. Sends a structured prompt to the LLM
  4. Parses the LLM response into a DebugAnalysis result

The LLM acts as an expert verification engineer analyzing the waveform
and providing: violation cycle, signal trace, root cause classification,
suggested fix, and recommended follow-up properties.
"""

import re
import json
import logging
from typing import Optional
from dataclasses import dataclass, field

from app.services.llm_service import ollama_service
from app.services.formal_service import (
    get_job,
    read_counterexample_vcd,
    format_counterexample_for_llm,
    FormalJob,
)
from app.services.prompt_templates import get_system_prompt

logger = logging.getLogger("veriassist.debug")


# ═══════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════

@dataclass
class DebugAnalysis:
    """Structured result from LLM counterexample analysis."""
    # Summary
    summary: str = ""

    # Violation details
    violation_cycle: int = -1
    violation_assertion: str = ""
    violation_description: str = ""

    # Signal trace (key signals at violation)
    signal_trace: list[dict] = field(default_factory=list)

    # Root cause
    root_cause: str = ""
    classification: str = ""    # DESIGN_BUG | PROPERTY_ISSUE | CONSTRAINT_MISSING | RESET_ISSUE

    # Fix suggestions
    suggested_fix: str = ""
    fixed_code: str = ""        # corrected SVA or RTL snippet

    # Follow-up
    followup_properties: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    # Raw LLM response
    raw_response: str = ""

    # Metadata
    model_used: str = ""
    analysis_time: float = 0.0


# ═══════════════════════════════════════════════════════════════
# DEBUG PROMPT TEMPLATE
# ═══════════════════════════════════════════════════════════════

DEBUG_COUNTEREXAMPLE_PROMPT = """You are VeriAssist Debug Assistant — an expert VLSI verification engineer analyzing a formal verification counterexample.

A formal property check has FAILED. SymbiYosys found a counterexample trace that violates an assertion. Your job is to analyze the trace and explain what went wrong.

ANALYSIS INSTRUCTIONS:
1. IDENTIFY the exact cycle where the violation occurs
2. TRACE the signal values leading up to the violation
3. DETERMINE the root cause — what sequence of events caused the failure
4. CLASSIFY the issue as one of:
   - DESIGN_BUG: The RTL has a functional bug that needs to be fixed
   - PROPERTY_ISSUE: The SVA property is incorrect, over-constrained, or missing assumptions
   - CONSTRAINT_MISSING: The formal environment needs additional assume constraints on inputs
   - RESET_ISSUE: The failure is related to initialization or reset behavior
5. SUGGEST a specific fix with corrected code
6. RECOMMEND follow-up properties to verify after the fix

FORMAT YOUR RESPONSE EXACTLY AS FOLLOWS (use these exact section headers):

## SUMMARY
One-sentence summary of the failure.

## VIOLATION
- Cycle: <cycle number>
- Assertion: <assertion name>
- Description: What happened at this cycle

## SIGNAL TRACE
Cycle-by-cycle values of key signals leading to the violation:
- Cycle N: signal1=val, signal2=val, ...
- Cycle N+1: signal1=val, signal2=val, ...

## ROOT CAUSE
Detailed explanation of why the assertion failed.

## CLASSIFICATION
<one of: DESIGN_BUG | PROPERTY_ISSUE | CONSTRAINT_MISSING | RESET_ISSUE>

## SUGGESTED FIX
Explanation of what to change.

```systemverilog
// corrected code here
```

## FOLLOW-UP PROPERTIES
- Property 1 description
- Property 2 description
"""


# ═══════════════════════════════════════════════════════════════
# MAIN DEBUG FUNCTION
# ═══════════════════════════════════════════════════════════════

class DebugService:
    """Analyzes formal verification counterexamples using LLM."""

    async def analyze_counterexample(
        self,
        job_id: str,
        dut_code: str = "",
        model: Optional[str] = None,
        temperature: float = 0.2,
    ) -> DebugAnalysis:
        """
        Analyze a failed formal job's counterexample.

        Args:
            job_id: ID of the failed formal job
            dut_code: optional DUT source code for deeper analysis
            model: Ollama model to use (None = default)
            temperature: LLM temperature (lower = more precise)

        Returns:
            DebugAnalysis with structured debug information
        """
        import time
        t0 = time.time()

        analysis = DebugAnalysis()

        # Get the job
        job = get_job(job_id)
        if not job:
            analysis.summary = f"Job '{job_id}' not found"
            return analysis

        if not job.result or job.result.status != "FAIL":
            analysis.summary = "Job did not fail — no counterexample to analyze"
            return analysis

        # Extract failed assertion info
        failed = job.result.failed_assertions
        if failed:
            analysis.violation_assertion = failed[0].get("name", "unknown")
            analysis.violation_cycle = failed[0].get("step", -1)

        # Read VCD counterexample
        vcd_summary = ""
        if job.result.counterexample_vcd:
            vcd_data = read_counterexample_vcd(job.result.counterexample_vcd)
            vcd_summary = format_counterexample_for_llm(vcd_data)
        else:
            vcd_summary = "No VCD trace available."

        # Build the debug prompt
        prompt = self._build_debug_prompt(
            job=job,
            vcd_summary=vcd_summary,
            dut_code=dut_code,
        )

        # Call LLM
        logger.info(f"[{job_id}] Sending counterexample to LLM for analysis...")
        try:
            messages = [
                {"role": "system", "content": DEBUG_COUNTEREXAMPLE_PROMPT},
                {"role": "user", "content": prompt},
            ]

            response = await ollama_service.chat(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=4096,
            )

            analysis.raw_response = response
            analysis.model_used = model or "default"

            # Parse the structured response
            self._parse_debug_response(response, analysis)

        except Exception as e:
            logger.error(f"[{job_id}] LLM analysis failed: {e}")
            analysis.summary = f"LLM analysis failed: {e}"

        analysis.analysis_time = time.time() - t0
        logger.info(
            f"[{job_id}] Debug analysis complete: {analysis.classification} "
            f"({analysis.analysis_time:.1f}s)"
        )

        return analysis

    # ── Prompt Building ───────────────────────────────────

    def _build_debug_prompt(
        self,
        job: FormalJob,
        vcd_summary: str,
        dut_code: str,
    ) -> str:
        """Build the complete user prompt for counterexample analysis."""
        sections = []

        # Failed assertion info
        failed = job.result.failed_assertions if job.result else []
        sections.append("=== FAILED ASSERTION ===")
        if failed:
            for fa in failed:
                sections.append(f"Name: {fa.get('name', 'unknown')}")
                sections.append(f"File: {fa.get('file', 'unknown')}")
                sections.append(f"Line: {fa.get('line', '?')}")
                sections.append(f"Step (cycle): {fa.get('step', '?')}")
        else:
            sections.append("No specific assertion info available.")

        # SVA code
        sections.append("\n=== SVA PROPERTIES (original) ===")
        sections.append(job.sva_code if job.sva_code else "Not available")

        # Lowered RTL
        if job.lowered_rtl:
            sections.append("\n=== LOWERED RTL (what SymbiYosys verified) ===")
            sections.append(job.lowered_rtl)

        # DUT code
        if dut_code:
            sections.append("\n=== DUT SOURCE CODE ===")
            sections.append(dut_code)
        elif job.dut_code:
            sections.append("\n=== DUT SOURCE CODE ===")
            sections.append(job.dut_code)

        # Counterexample trace
        sections.append("\n=== COUNTEREXAMPLE TRACE (from VCD) ===")
        sections.append(vcd_summary)

        # Formal settings
        sections.append(f"\n=== FORMAL SETTINGS ===")
        sections.append(f"Mode: {job.mode}")
        sections.append(f"Depth: {job.depth}")
        sections.append(f"Solver: {job.solver or 'yices (default)'}")

        # Engine output summary
        if job.result and job.result.engine_output:
            output_lines = job.result.engine_output.strip().split("\n")
            relevant = [l for l in output_lines if "assert" in l.lower() or "fail" in l.lower() or "error" in l.lower()]
            if relevant:
                sections.append("\n=== SYMBIYOSYS OUTPUT (relevant lines) ===")
                sections.extend(relevant[-10:])

        return "\n".join(sections)

    # ── Response Parsing ──────────────────────────────────

    def _parse_debug_response(self, response: str, analysis: DebugAnalysis):
        """Parse the LLM's structured response into DebugAnalysis fields."""

        # Extract SUMMARY
        summary_match = re.search(r'## SUMMARY\s*\n(.*?)(?=\n## |\Z)', response, re.DOTALL)
        if summary_match:
            analysis.summary = summary_match.group(1).strip()

        # Extract VIOLATION
        violation_match = re.search(r'## VIOLATION\s*\n(.*?)(?=\n## |\Z)', response, re.DOTALL)
        if violation_match:
            vtext = violation_match.group(1)
            analysis.violation_description = vtext.strip()

            # Parse cycle number
            cycle_match = re.search(r'Cycle:\s*(\d+)', vtext)
            if cycle_match and analysis.violation_cycle < 0:
                analysis.violation_cycle = int(cycle_match.group(1))

            # Parse assertion name
            assert_match = re.search(r'Assertion:\s*(\S+)', vtext)
            if assert_match and not analysis.violation_assertion:
                analysis.violation_assertion = assert_match.group(1)

        # Extract SIGNAL TRACE
        trace_match = re.search(r'## SIGNAL TRACE\s*\n(.*?)(?=\n## |\Z)', response, re.DOTALL)
        if trace_match:
            trace_text = trace_match.group(1).strip()
            for line in trace_text.split("\n"):
                line = line.strip().lstrip("- ")
                if line and "cycle" in line.lower():
                    analysis.signal_trace.append({"description": line})

        # Extract ROOT CAUSE
        cause_match = re.search(r'## ROOT CAUSE\s*\n(.*?)(?=\n## |\Z)', response, re.DOTALL)
        if cause_match:
            analysis.root_cause = cause_match.group(1).strip()

        # Extract CLASSIFICATION
        class_match = re.search(r'## CLASSIFICATION\s*\n\s*(DESIGN_BUG|PROPERTY_ISSUE|CONSTRAINT_MISSING|RESET_ISSUE)', response)
        if class_match:
            analysis.classification = class_match.group(1)
        else:
            # Try to infer from text
            text_lower = response.lower()
            if "design bug" in text_lower or "rtl bug" in text_lower:
                analysis.classification = "DESIGN_BUG"
            elif "property" in text_lower and ("incorrect" in text_lower or "over-constrained" in text_lower):
                analysis.classification = "PROPERTY_ISSUE"
            elif "constraint" in text_lower or "assume" in text_lower:
                analysis.classification = "CONSTRAINT_MISSING"
            elif "reset" in text_lower or "initial" in text_lower:
                analysis.classification = "RESET_ISSUE"
            else:
                analysis.classification = "UNKNOWN"

        # Extract SUGGESTED FIX
        fix_match = re.search(r'## SUGGESTED FIX\s*\n(.*?)(?=\n## |\Z)', response, re.DOTALL)
        if fix_match:
            fix_text = fix_match.group(1).strip()
            analysis.suggested_fix = fix_text

            # Extract code block from fix
            code_match = re.search(r'```(?:systemverilog|sv|verilog)?\s*\n(.*?)```', fix_text, re.DOTALL)
            if code_match:
                analysis.fixed_code = code_match.group(1).strip()

        # Extract FOLLOW-UP PROPERTIES
        followup_match = re.search(r'## FOLLOW-UP PROPERTIES\s*\n(.*?)(?=\n## |\Z)', response, re.DOTALL)
        if followup_match:
            for line in followup_match.group(1).strip().split("\n"):
                line = line.strip().lstrip("- ")
                if line:
                    analysis.followup_properties.append(line)


# ═══════════════════════════════════════════════════════════════
# QUICK DEBUG (for API use without job tracking)
# ═══════════════════════════════════════════════════════════════

async def quick_debug_analysis(
    sva_code: str,
    dut_code: str,
    failed_assertion: str,
    violation_step: int,
    vcd_summary: str = "",
    model: Optional[str] = None,
) -> DebugAnalysis:
    """
    Standalone debug analysis without requiring a formal job.
    Useful for analyzing failures from external tools or manual runs.
    """
    analysis = DebugAnalysis(
        violation_assertion=failed_assertion,
        violation_cycle=violation_step,
    )

    prompt_parts = [
        "=== FAILED ASSERTION ===",
        f"Name: {failed_assertion}",
        f"Step: {violation_step}",
        "\n=== SVA PROPERTIES ===",
        sva_code,
    ]

    if dut_code:
        prompt_parts.append("\n=== DUT SOURCE CODE ===")
        prompt_parts.append(dut_code)

    if vcd_summary:
        prompt_parts.append("\n=== COUNTEREXAMPLE TRACE ===")
        prompt_parts.append(vcd_summary)

    try:
        messages = [
            {"role": "system", "content": DEBUG_COUNTEREXAMPLE_PROMPT},
            {"role": "user", "content": "\n".join(prompt_parts)},
        ]

        response = await ollama_service.chat(
            messages=messages,
            model=model,
            temperature=0.2,
            max_tokens=4096,
        )

        analysis.raw_response = response
        debug_service._parse_debug_response(response, analysis)

    except Exception as e:
        analysis.summary = f"Analysis failed: {e}"

    return analysis


# ═══════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════

debug_service = DebugService()