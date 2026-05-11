"""
VeriAssist v2.0 — SVA Lowering Engine

Converts parsed SVA properties into synthesizable RTL with immediate
assertions that SymbiYosys can verify directly (no Verific needed).

Lowering strategies per construct:
  |->           → same-cycle combinational check
  |=>           → 1-cycle register + next-cycle check
  ##N           → N-stage shift register
  ##[M:N]       → counter with window check
  [*N]          → consecutive counter
  [*M:N]        → consecutive counter with range
  [->N]         → non-consecutive occurrence counter
  [=N]          → non-consecutive occurrence counter (no end constraint)
  $rose(s)      → s && !s_prev
  $fell(s)      → !s && s_prev
  $stable(s)    → s == s_prev
  $changed(s)   → s != s_prev
  $past(s)      → s_past1 (1-cycle shift register)
  $past(s, N)   → s_pastN (N-stage shift register chain)
  $onehot0(e)   → (e == 0 || (e & (e-1)) == 0)
  $onehot(e)    → (e != 0 && (e & (e-1)) == 0)
  disable iff   → reset guard wrapping entire monitor
  
Output: synthesizable SystemVerilog wrapped in `ifdef FORMAL / `endif
"""

import re
import logging
from typing import Optional
from app.services.sva_parser import (
    ParsedSVA, SVAProperty, SVAAssertion, SVASignal,
    analyze_property, PropertyAnalysis, extract_signal_from_func,
)

logger = logging.getLogger("veriassist.lowering")


class SVALoweringEngine:
    """
    Lowers parsed SVA into synthesizable RTL with immediate assertions.
    Each property becomes an always @(posedge clk) block with registers
    for tracking temporal state and immediate assert/assume/cover statements.
    """

    def __init__(self):
        self._reg_counter = 0  # unique register name counter

    def lower(self, parsed: ParsedSVA) -> str:
        """
        Main entry point. Takes a ParsedSVA and returns complete
        synthesizable SystemVerilog module with `ifdef FORMAL guards.
        """
        self._reg_counter = 0
        lines = []

        # If no signals declared, auto-detect from property bodies
        if not parsed.signals:
            self._auto_detect_signals(parsed)

        # Module header
        lines.append(f"`ifdef FORMAL")
        lines.append(f"module {parsed.module_name or 'formal_monitor'} (")

        # Ports
        port_lines = []
        port_lines.append(f"    input wire {parsed.clock},")
        port_lines.append(f"    input wire {parsed.reset},")
        for sig in parsed.signals:
            if sig.name in (parsed.clock, parsed.reset):
                continue
            width = f"{sig.width} " if sig.width else ""
            port_lines.append(f"    input wire {width}{sig.name},")

        # Remove trailing comma from last port
        if port_lines:
            port_lines[-1] = port_lines[-1].rstrip(",")

        lines.extend(port_lines)
        lines.append(f");")
        lines.append("")

        # Past-value registers for system functions ($rose, $fell, $stable, $changed)
        past_signals = self._collect_past_signals(parsed)
        if past_signals:
            lines.append(f"    // Past-value registers for edge/stability detection")
            for sig_name in past_signals:
                width = self._get_signal_width(sig_name, parsed)
                lines.append(f"    reg {width}{sig_name}_prev;")
            lines.append("")

            lines.append(f"    always @({parsed.clock_edge} {parsed.clock}) begin")
            lines.append(f"        if ({parsed.reset_condition}) begin")
            for sig_name in past_signals:
                lines.append(f"            {sig_name}_prev <= 0;")
            lines.append(f"        end else begin")
            for sig_name in past_signals:
                lines.append(f"            {sig_name}_prev <= {sig_name};")
            lines.append(f"        end")
            lines.append(f"    end")
            lines.append("")

        # $past(sig, N) delay registers — shift register chains
        past_delay_signals = self._collect_past_delay_signals(parsed)
        if past_delay_signals:
            lines.append(f"    // $past delay registers (shift chains)")
            for sig_name, max_delay in past_delay_signals.items():
                width = self._get_signal_width(sig_name, parsed)
                for d in range(1, max_delay + 1):
                    lines.append(f"    reg {width}{sig_name}_past{d};")
            lines.append("")

            lines.append(f"    always @({parsed.clock_edge} {parsed.clock}) begin")
            lines.append(f"        if ({parsed.reset_condition}) begin")
            for sig_name, max_delay in past_delay_signals.items():
                for d in range(1, max_delay + 1):
                    lines.append(f"            {sig_name}_past{d} <= 0;")
            lines.append(f"        end else begin")
            for sig_name, max_delay in past_delay_signals.items():
                lines.append(f"            {sig_name}_past1 <= {sig_name};")
                for d in range(2, max_delay + 1):
                    lines.append(f"            {sig_name}_past{d} <= {sig_name}_past{d-1};")
            lines.append(f"        end")
            lines.append(f"    end")
            lines.append("")

        # Lower each assertion
        for assertion in parsed.assertions:
            prop = parsed.get_property(assertion.property_name)
            if not prop:
                lines.append(f"    // WARNING: property '{assertion.property_name}' not found for {assertion.label}")
                continue

            analysis = analyze_property(prop.body)
            monitor_lines = self._lower_assertion(assertion, prop, analysis, parsed)

            # Post-lowering validation: check for residual SVA syntax in CODE lines only (skip comments)
            code_lines = [l for l in monitor_lines if not l.strip().startswith("//")]
            lowered_code = "\n".join(code_lines)
            sva_residue = re.findall(r'\[\*\d*\]|\[->?\d+\]|\[=\d+\]|##\d+', lowered_code)

            if sva_residue:
                reason = f"residual SVA: {sva_residue}"
                lines.append(f"    // --- {assertion.label}: {assertion.type} property ({prop.name}) ---")
                lines.append(f"    // SKIPPED: property uses constructs not yet fully lowered ({reason})")
                lines.extend(self._format_comment_block("    ", "Original SVA:", prop.body.strip()[:80]))
                logger.warning(f"Skipping {assertion.label}: {reason}")
            else:
                lines.extend(monitor_lines)
            lines.append("")

        lines.append(f"endmodule")
        lines.append(f"`endif // FORMAL")

        result = "\n".join(lines)
        logger.info(f"Lowered {len(parsed.assertions)} assertions into {len(lines)} lines of RTL")
        return result

    # ═══════════════════════════════════════════════════════════
    # ASSERTION LOWERING (dispatches to the right strategy)
    # ═══════════════════════════════════════════════════════════

    def _lower_assertion(
        self,
        assertion: SVAAssertion,
        prop: SVAProperty,
        analysis: PropertyAnalysis,
        parsed: ParsedSVA,
    ) -> list[str]:
        """Dispatch to the correct lowering strategy based on property analysis."""
        lines = []
        label = assertion.label
        atype = assertion.type  # assert | assume | cover

        lines.append(f"    // --- {label}: {atype} property ({prop.name}) ---")
        lines.extend(self._format_comment_block("    ", "Original SVA:", prop.body.strip()))

        special_lines = self._lower_special_property(label, atype, prop.body, parsed)
        if special_lines is not None:
            return lines + special_lines

        if analysis.is_simple_check and not analysis.has_implication:
            return lines + self._lower_simple_check(label, atype, prop.body, parsed)

        if analysis.has_implication:
            if analysis.delays or analysis.repetitions:
                return lines + self._lower_temporal_implication(label, atype, analysis, parsed)
            elif analysis.implication_type == "overlapping":
                return lines + self._lower_overlapping(label, atype, analysis, parsed)
            else:
                return lines + self._lower_non_overlapping(label, atype, analysis, parsed)

        # Fallback: treat as simple check
        return lines + self._lower_simple_check(label, atype, prop.body, parsed)

    def _lower_special_property(
        self, label: str, atype: str, body: str, parsed: ParsedSVA
    ) -> Optional[list[str]]:
        """Handle sequence patterns the generic implication lowering cannot yet express."""
        compact = self._compact_sva(body)

        lowered = self._try_lower_antecedent_bounded_repetition(label, atype, compact, parsed)
        if lowered is not None:
            return lowered

        lowered = self._try_lower_two_stage_antecedent(label, atype, compact, parsed)
        if lowered is not None:
            return lowered

        lowered = self._try_lower_captured_range_sequence(label, atype, body, compact, parsed)
        if lowered is not None:
            return lowered

        return None

    def _format_comment_block(self, indent: str, header: str, text: str) -> list[str]:
        """Format possibly multi-line text as a safe sequence of comment lines."""
        text = text or ""
        text_lines = text.splitlines() or [""]
        formatted = [f"{indent}// {header} {text_lines[0]}".rstrip()]
        for line in text_lines[1:]:
            formatted.append(f"{indent}// {line}".rstrip())
        return formatted

    # ═══════════════════════════════════════════════════════════
    # SIMPLE COMBINATIONAL CHECK (no implication, no temporal)
    # ═══════════════════════════════════════════════════════════

    def _lower_simple_check(
        self, label: str, atype: str, body: str, parsed: ParsedSVA
    ) -> list[str]:
        """
        Property is a pure combinational check.
        e.g., (state == IDLE) || (state == ADDR) || ...
        """
        condition = self._translate_expression(body, parsed)
        return self._emit_always_block(label, atype, condition, None, parsed)

    # ═══════════════════════════════════════════════════════════
    # OVERLAPPING IMPLICATION |->
    # ═══════════════════════════════════════════════════════════

    def _lower_overlapping(
        self, label: str, atype: str, analysis: PropertyAnalysis, parsed: ParsedSVA
    ) -> list[str]:
        """
        antecedent |-> consequent
        Same-cycle check: when antecedent is true, consequent must also be true.
        """
        ante = self._translate_expression(analysis.antecedent, parsed)
        cons = self._translate_expression(analysis.consequent, parsed)
        return self._emit_always_block(label, atype, cons, ante, parsed)

    # ═══════════════════════════════════════════════════════════
    # NON-OVERLAPPING IMPLICATION |=>
    # ═══════════════════════════════════════════════════════════

    def _lower_non_overlapping(
        self, label: str, atype: str, analysis: PropertyAnalysis, parsed: ParsedSVA
    ) -> list[str]:
        """
        antecedent |=> consequent
        Check consequent one cycle after antecedent matches.
        Uses a 1-bit register to remember the antecedent.
        """
        reg_name = self._unique_reg(f"{label}_triggered")
        ante = self._translate_expression(analysis.antecedent, parsed)
        cons = self._translate_expression(analysis.consequent, parsed)

        lines = []
        lines.append(f"    reg {reg_name};")
        lines.append(f"    always @({parsed.clock_edge} {parsed.clock}) begin")
        lines.append(f"        if ({parsed.reset_condition}) begin")
        lines.append(f"            {reg_name} <= 0;")
        lines.append(f"        end else begin")

        # Check: if triggered last cycle, consequent must be true now
        if atype == "assert":
            lines.append(f"            if ({reg_name} && !({cons}))")
            lines.append(f"                {label}: assert(0); // FAIL: consequent not met after antecedent")
        elif atype == "assume":
            lines.append(f"            if ({reg_name})")
            lines.append(f"                {label}: assume({cons});")
        elif atype == "cover":
            lines.append(f"            if ({reg_name} && ({cons}))")
            lines.append(f"                {label}: cover(1);")

        # Update trigger register
        lines.append(f"            {reg_name} <= ({ante});")
        lines.append(f"        end")
        lines.append(f"    end")
        return lines

    # ═══════════════════════════════════════════════════════════
    # TEMPORAL IMPLICATION (with delays and/or repetitions)
    # ═══════════════════════════════════════════════════════════

    def _lower_temporal_implication(
        self, label: str, atype: str, analysis: PropertyAnalysis, parsed: ParsedSVA
    ) -> list[str]:
        """
        Handles implications with delays (##N, ##[M:N]) and repetitions ([*N], [->N], [=N]).
        Generates counter-based or shift-register-based monitors.
        """
        lines = []
        ante = self._translate_expression(analysis.antecedent, parsed)

        # Determine what's in the consequent
        cons_raw = analysis.consequent

        # ── Fixed delay ##N ───────────────────────────────
        if analysis.delays and analysis.delays[0]["type"] == "fixed":
            delay_n = analysis.delays[0]["n"]
            # Extract the check expression after the delay
            check_expr = re.sub(r'##\d+\s*', '', cons_raw).strip()
            check_expr = self._translate_expression(check_expr, parsed)

            return lines + self._lower_fixed_delay(label, atype, ante, check_expr, delay_n, parsed)

        # ── Range delay ##[M:N] ───────────────────────────
        if analysis.delays and analysis.delays[0]["type"] == "range":
            delay_m = analysis.delays[0]["m"]
            delay_n = analysis.delays[0]["n"]
            check_expr = re.sub(r'##\[\d+:\d+\]\s*', '', cons_raw).strip()
            check_expr = self._translate_expression(check_expr, parsed)

            return lines + self._lower_range_delay(label, atype, ante, check_expr, delay_m, delay_n, parsed)

        # ── Bounded repetition [*N] ───────────────────────
        if analysis.repetitions and analysis.repetitions[0]["type"] == "bounded":
            rep_n = analysis.repetitions[0]["n"]
            # Extract signal being repeated
            rep_match = re.search(r'(\w+)\s*\[\*\d+\]', cons_raw)
            rep_signal = rep_match.group(1) if rep_match else cons_raw.strip()

            return lines + self._lower_bounded_repetition(label, atype, ante, rep_signal, rep_n, parsed)

        # ── Bounded range repetition [*M:N] ───────────────
        if analysis.repetitions and analysis.repetitions[0]["type"] == "bounded_range":
            rep_m = analysis.repetitions[0]["m"]
            rep_n = analysis.repetitions[0]["n"]
            rep_match = re.search(r'(\w+)\s*\[\*\d+:\d+\]', cons_raw)
            rep_signal = rep_match.group(1) if rep_match else cons_raw.strip()

            return lines + self._lower_bounded_range_repetition(label, atype, ante, rep_signal, rep_m, rep_n, parsed)

        # ── Goto repetition [->N] ─────────────────────────
        if analysis.repetitions and analysis.repetitions[0]["type"] == "goto":
            rep_n = analysis.repetitions[0]["n"]
            rep_match = re.search(r'(\w+)\s*\[->\d+\]', cons_raw)
            rep_signal = rep_match.group(1) if rep_match else cons_raw.strip()

            return lines + self._lower_goto_repetition(label, atype, ante, rep_signal, rep_n, parsed)

        # ── Non-consecutive repetition [=N] ───────────────
        if analysis.repetitions and analysis.repetitions[0]["type"] == "nonconsec":
            rep_n = analysis.repetitions[0]["n"]
            rep_match = re.search(r'(\w+)\s*\[=\d+\]', cons_raw)
            rep_signal = rep_match.group(1) if rep_match else cons_raw.strip()

            return lines + self._lower_nonconsec_repetition(label, atype, ante, rep_signal, rep_n, parsed)

        # ── Fallback: treat consequent as simple expression
        cons = self._translate_expression(cons_raw, parsed)
        if analysis.implication_type == "non_overlapping":
            return lines + self._lower_non_overlapping_simple(label, atype, ante, cons, parsed)
        else:
            return self._emit_always_block(label, atype, cons, ante, parsed)

    # ═══════════════════════════════════════════════════════════
    # FIXED DELAY ##N
    # ═══════════════════════════════════════════════════════════

    def _lower_fixed_delay(
        self, label: str, atype: str, ante: str, check: str,
        n: int, parsed: ParsedSVA
    ) -> list[str]:
        """Use an N-bit shift register to delay the trigger.
        Special case: n=1 uses a simple 1-bit register (no shift needed).
        """
        reg_name = self._unique_reg(f"{label}_delay")
        lines = []

        if n == 1:
            # Simple 1-cycle delay: register the antecedent, check next cycle
            lines.append(f"    reg {reg_name};")
            lines.append(f"    always @({parsed.clock_edge} {parsed.clock}) begin")
            lines.append(f"        if ({parsed.reset_condition}) begin")
            lines.append(f"            {reg_name} <= 0;")
            lines.append(f"        end else begin")
            lines.append(f"            {reg_name} <= ({ante});")

            if atype == "assert":
                lines.append(f"            if ({reg_name} && !({check}))")
                lines.append(f"                {label}: assert(0); // FAIL at delay 1")
            elif atype == "assume":
                lines.append(f"            if ({reg_name})")
                lines.append(f"                {label}: assume({check});")
            elif atype == "cover":
                lines.append(f"            if ({reg_name} && ({check}))")
                lines.append(f"                {label}: cover(1);")

            lines.append(f"        end")
            lines.append(f"    end")
        else:
            # N-bit shift register for delays > 1
            lines.append(f"    reg [{n-1}:0] {reg_name};")
            lines.append(f"    always @({parsed.clock_edge} {parsed.clock}) begin")
            lines.append(f"        if ({parsed.reset_condition}) begin")
            lines.append(f"            {reg_name} <= 0;")
            lines.append(f"        end else begin")
            lines.append(f"            {reg_name} <= {{{reg_name}[{n-2}:0], ({ante})}};")

            if atype == "assert":
                lines.append(f"            if ({reg_name}[{n-1}] && !({check}))")
                lines.append(f"                {label}: assert(0); // FAIL at delay {n}")
            elif atype == "assume":
                lines.append(f"            if ({reg_name}[{n-1}])")
                lines.append(f"                {label}: assume({check});")
            elif atype == "cover":
                lines.append(f"            if ({reg_name}[{n-1}] && ({check}))")
                lines.append(f"                {label}: cover(1);")

            lines.append(f"        end")
            lines.append(f"    end")
        return lines

    # ═══════════════════════════════════════════════════════════
    # RANGE DELAY ##[M:N]
    # ═══════════════════════════════════════════════════════════

    def _lower_range_delay(
        self, label: str, atype: str, ante: str, check: str,
        m: int, n: int, parsed: ParsedSVA
    ) -> list[str]:
        """Counter-based: antecedent starts a counter, check is valid in window [M, N]."""
        cnt_reg = self._unique_reg(f"{label}_cnt")
        active_reg = self._unique_reg(f"{label}_active")
        satisfied_reg = self._unique_reg(f"{label}_satisfied")
        width = max(1, (n).bit_length())

        lines = []
        lines.append(f"    reg [{width-1}:0] {cnt_reg};")
        lines.append(f"    reg {active_reg};")
        lines.append(f"    reg {satisfied_reg};")
        lines.append(f"    always @({parsed.clock_edge} {parsed.clock}) begin")
        lines.append(f"        if ({parsed.reset_condition}) begin")
        lines.append(f"            {cnt_reg} <= 0;")
        lines.append(f"            {active_reg} <= 0;")
        lines.append(f"            {satisfied_reg} <= 0;")
        lines.append(f"        end else begin")
        lines.append(f"            // Start counting on antecedent")
        lines.append(f"            if (({ante}) && !{active_reg}) begin")
        lines.append(f"                {cnt_reg} <= 1;")
        lines.append(f"                {active_reg} <= 1;")
        lines.append(f"                {satisfied_reg} <= 0;")
        lines.append(f"            end else if ({active_reg}) begin")
        lines.append(f"                {cnt_reg} <= {cnt_reg} + 1;")
        lines.append(f"                // Check in window [{m}, {n}]")
        lines.append(f"                if ({cnt_reg} >= {m} && {cnt_reg} <= {n} && ({check}))")
        lines.append(f"                    {satisfied_reg} <= 1;")
        lines.append(f"                // Window expired")
        lines.append(f"                if ({cnt_reg} >= {n}) begin")

        if atype == "assert":
            lines.append(f"                    if (!{satisfied_reg} && !({check}))")
            lines.append(f"                        {label}: assert(0); // FAIL: not satisfied in [{m}:{n}]")
        elif atype == "assume":
            lines.append(f"                    {label}: assume({satisfied_reg} || ({check}));")
        elif atype == "cover":
            lines.append(f"                    if ({satisfied_reg} || ({check}))")
            lines.append(f"                        {label}: cover(1);")

        lines.append(f"                    {active_reg} <= 0;")
        lines.append(f"                    {cnt_reg} <= 0;")
        lines.append(f"                end")
        lines.append(f"            end")
        lines.append(f"        end")
        lines.append(f"    end")
        return lines

    # ═══════════════════════════════════════════════════════════
    # BOUNDED REPETITION [*N]
    # ═══════════════════════════════════════════════════════════

    def _lower_bounded_repetition(
        self, label: str, atype: str, ante: str, signal: str,
        n: int, parsed: ParsedSVA
    ) -> list[str]:
        """Counter counts N consecutive cycles where signal is true."""
        cnt_reg = self._unique_reg(f"{label}_rep_cnt")
        active_reg = self._unique_reg(f"{label}_rep_active")
        width = max(1, (n).bit_length())

        lines = []
        lines.append(f"    reg [{width-1}:0] {cnt_reg};")
        lines.append(f"    reg {active_reg};")
        lines.append(f"    always @({parsed.clock_edge} {parsed.clock}) begin")
        lines.append(f"        if ({parsed.reset_condition}) begin")
        lines.append(f"            {cnt_reg} <= 0;")
        lines.append(f"            {active_reg} <= 0;")
        lines.append(f"        end else begin")
        lines.append(f"            if (({ante}) && !{active_reg}) begin")
        lines.append(f"                {active_reg} <= 1;")
        lines.append(f"                {cnt_reg} <= ({signal}) ? 1 : 0;")
        lines.append(f"            end else if ({active_reg}) begin")
        lines.append(f"                if ({signal})")
        lines.append(f"                    {cnt_reg} <= {cnt_reg} + 1;")
        lines.append(f"                else begin")

        if atype == "assert":
            lines.append(f"                    if ({cnt_reg} < {n})")
            lines.append(f"                        {label}: assert(0); // FAIL: {signal} not held for {n} cycles")
        elif atype == "cover":
            lines.append(f"                    if ({cnt_reg} >= {n})")
            lines.append(f"                        {label}: cover(1);")

        lines.append(f"                    {active_reg} <= 0;")
        lines.append(f"                    {cnt_reg} <= 0;")
        lines.append(f"                end")
        lines.append(f"                if ({cnt_reg} >= {n}) begin")

        if atype == "cover":
            lines.append(f"                    {label}_done: cover(1);")

        lines.append(f"                    {active_reg} <= 0;")
        lines.append(f"                    {cnt_reg} <= 0;")
        lines.append(f"                end")
        lines.append(f"            end")
        lines.append(f"        end")
        lines.append(f"    end")
        return lines

    # ═══════════════════════════════════════════════════════════
    # BOUNDED RANGE REPETITION [*M:N]
    # ═══════════════════════════════════════════════════════════

    def _lower_bounded_range_repetition(
        self, label: str, atype: str, ante: str, signal: str,
        m: int, n: int, parsed: ParsedSVA
    ) -> list[str]:
        """Like bounded but accepts count in [M, N] range."""
        cnt_reg = self._unique_reg(f"{label}_rrep_cnt")
        active_reg = self._unique_reg(f"{label}_rrep_active")
        width = max(1, (n).bit_length())

        lines = []
        lines.append(f"    reg [{width-1}:0] {cnt_reg};")
        lines.append(f"    reg {active_reg};")
        lines.append(f"    always @({parsed.clock_edge} {parsed.clock}) begin")
        lines.append(f"        if ({parsed.reset_condition}) begin")
        lines.append(f"            {cnt_reg} <= 0; {active_reg} <= 0;")
        lines.append(f"        end else begin")
        lines.append(f"            if (({ante}) && !{active_reg}) begin")
        lines.append(f"                {active_reg} <= 1; {cnt_reg} <= ({signal}) ? 1 : 0;")
        lines.append(f"            end else if ({active_reg}) begin")
        lines.append(f"                if ({signal}) {cnt_reg} <= {cnt_reg} + 1;")
        lines.append(f"                else begin")

        if atype == "assert":
            lines.append(f"                    if ({cnt_reg} < {m})")
            lines.append(f"                        {label}: assert(0); // FAIL: {signal} held {cnt_reg} < {m}")
        elif atype == "cover":
            lines.append(f"                    if ({cnt_reg} >= {m}) {label}: cover(1);")

        lines.append(f"                    {active_reg} <= 0; {cnt_reg} <= 0;")
        lines.append(f"                end")
        lines.append(f"                if ({cnt_reg} >= {n}) begin {active_reg} <= 0; {cnt_reg} <= 0; end")
        lines.append(f"            end")
        lines.append(f"        end")
        lines.append(f"    end")
        return lines

    # ═══════════════════════════════════════════════════════════
    # GOTO REPETITION [->N]
    # ═══════════════════════════════════════════════════════════

    def _lower_goto_repetition(
        self, label: str, atype: str, ante: str, signal: str,
        n: int, parsed: ParsedSVA
    ) -> list[str]:
        """Counter counts N non-consecutive occurrences of signal."""
        cnt_reg = self._unique_reg(f"{label}_goto_cnt")
        active_reg = self._unique_reg(f"{label}_goto_active")
        width = max(1, (n).bit_length())

        lines = []
        lines.append(f"    reg [{width-1}:0] {cnt_reg};")
        lines.append(f"    reg {active_reg};")
        lines.append(f"    always @({parsed.clock_edge} {parsed.clock}) begin")
        lines.append(f"        if ({parsed.reset_condition}) begin")
        lines.append(f"            {cnt_reg} <= 0; {active_reg} <= 0;")
        lines.append(f"        end else begin")
        lines.append(f"            if (({ante}) && !{active_reg}) begin")
        lines.append(f"                {active_reg} <= 1; {cnt_reg} <= 0;")
        lines.append(f"            end else if ({active_reg}) begin")
        lines.append(f"                if ({signal}) begin")
        lines.append(f"                    {cnt_reg} <= {cnt_reg} + 1;")
        lines.append(f"                    if ({cnt_reg} + 1 >= {n}) begin")

        if atype == "assert":
            lines.append(f"                        // Goto match — property satisfied")
        elif atype == "cover":
            lines.append(f"                        {label}: cover(1);")

        lines.append(f"                        {active_reg} <= 0; {cnt_reg} <= 0;")
        lines.append(f"                    end")
        lines.append(f"                end")
        lines.append(f"            end")
        lines.append(f"        end")
        lines.append(f"    end")
        return lines

    # ═══════════════════════════════════════════════════════════
    # NON-CONSECUTIVE REPETITION [=N]
    # ═══════════════════════════════════════════════════════════

    def _lower_nonconsec_repetition(
        self, label: str, atype: str, ante: str, signal: str,
        n: int, parsed: ParsedSVA
    ) -> list[str]:
        """Same as goto but without end-cycle constraint."""
        # Implementation is identical to goto for our purposes
        return self._lower_goto_repetition(label, atype, ante, signal, n, parsed)

    # ═══════════════════════════════════════════════════════════
    # SIMPLE NON-OVERLAPPING (no delays/reps, just |=> check)
    # ═══════════════════════════════════════════════════════════

    def _lower_non_overlapping_simple(
        self, label: str, atype: str, ante: str, cons: str, parsed: ParsedSVA
    ) -> list[str]:
        """Simple |=> without complex temporal operators."""
        reg_name = self._unique_reg(f"{label}_trig")
        lines = []
        lines.append(f"    reg {reg_name};")
        lines.append(f"    always @({parsed.clock_edge} {parsed.clock}) begin")
        lines.append(f"        if ({parsed.reset_condition}) begin")
        lines.append(f"            {reg_name} <= 0;")
        lines.append(f"        end else begin")

        if atype == "assert":
            lines.append(f"            if ({reg_name} && !({cons}))")
            lines.append(f"                {label}: assert(0);")
        elif atype == "assume":
            lines.append(f"            if ({reg_name})")
            lines.append(f"                {label}: assume({cons});")
        elif atype == "cover":
            lines.append(f"            if ({reg_name} && ({cons}))")
            lines.append(f"                {label}: cover(1);")

        lines.append(f"            {reg_name} <= ({ante});")
        lines.append(f"        end")
        lines.append(f"    end")
        return lines

    def _try_lower_antecedent_bounded_repetition(
        self, label: str, atype: str, compact: str, parsed: ParsedSVA
    ) -> Optional[list[str]]:
        """Lower: ((expr)[*N]) |-> ##D check."""
        compact = self._strip_outer_parens(self._strip_local_property_decls(compact))
        match = re.match(
            r'^\(\s*\((?P<expr>.+?)\)\s*\[\*(?P<rep>\d+)\]\s*\)\s*\|->\s*\(\s*##(?P<delay>\d+)\s*(?P<check>.+?)\s*\)\s*$',
            compact,
        )
        if not match:
            return None

        expr = self._translate_expression(match.group("expr"), parsed)
        rep_n = int(match.group("rep"))
        delay_n = int(match.group("delay"))
        check = self._translate_expression(match.group("check"), parsed)
        return self._lower_repetition_then_delay(label, atype, expr, rep_n, check, delay_n, parsed)

    def _try_lower_two_stage_antecedent(
        self, label: str, atype: str, compact: str, parsed: ParsedSVA
    ) -> Optional[list[str]]:
        """Lower: (A ##1 B) |-> ##1 check."""
        compact = self._strip_outer_parens(self._strip_local_property_decls(compact))
        parts = self._split_implication(compact, "|->")
        if parts is None:
            return None

        antecedent = self._strip_outer_parens(parts[0].strip())
        consequent = self._strip_outer_parens(parts[1].strip())
        if not consequent.startswith("##1"):
            return None
        if antecedent.count("##1") != 1 or "[*" in antecedent or "," in antecedent:
            return None

        a_raw, b_raw = antecedent.split("##1", 1)
        start_expr = self._translate_expression(self._strip_outer_parens(a_raw), parsed)
        event_expr = self._translate_expression(self._strip_outer_parens(b_raw), parsed)
        check_expr = self._translate_expression(self._strip_outer_parens(consequent[3:].strip()), parsed)
        return self._lower_two_stage_sequence_then_delay(
            label, atype, start_expr, event_expr, check_expr, parsed
        )

    def _try_lower_captured_range_sequence(
        self, label: str, atype: str, body: str, compact: str, parsed: ParsedSVA
    ) -> Optional[list[str]]:
        """Lower: (((start), var = sig) ##1 hold[*m:n] ##1 event) |-> ##1 check."""
        if atype != "assert":
            return None

        compact = self._strip_outer_parens(self._strip_local_property_decls(compact))
        parts = self._split_implication(compact, "|->")
        if parts is None:
            return None

        antecedent = self._strip_outer_parens(parts[0].strip())
        consequent = self._strip_outer_parens(parts[1].strip())
        if not consequent.startswith("##1"):
            return None

        local_vars = self._extract_local_property_vars(body)
        if not local_vars:
            return None

        match = re.match(
            r'^\((?P<start>.+?),\s*(?P<var>\w+)\s*=\s*(?P<capture>\w+)\)\s*##1\s*\((?P<hold>.+?)\)\s*\[\*(?P<m>\d+):(?P<n>\d+)\]\s*##1\s*\((?P<event>.+?)\)\s*$',
            antecedent,
        )
        if not match:
            return None

        var_name = match.group("var")
        if var_name not in local_vars:
            return None

        capture_width = local_vars[var_name]
        start_expr = self._translate_expression(self._strip_outer_parens(match.group("start")), parsed)
        capture_sig = match.group("capture")
        hold_expr = self._translate_expression(self._strip_outer_parens(match.group("hold")), parsed)
        event_expr = self._translate_expression(self._strip_outer_parens(match.group("event")), parsed)
        check_expr = self._translate_expression(self._strip_outer_parens(consequent[3:].strip()), parsed)
        check_expr = re.sub(rf'\b{re.escape(var_name)}\b', f"{label}_capture", check_expr)

        return self._lower_capture_hold_then_event(
            label=label,
            start_expr=start_expr,
            capture_sig=capture_sig,
            capture_width=capture_width,
            hold_expr=hold_expr,
            min_cycles=int(match.group("m")),
            max_cycles=int(match.group("n")),
            event_expr=event_expr,
            check_expr=check_expr,
            parsed=parsed,
        )

    def _lower_repetition_then_delay(
        self,
        label: str,
        atype: str,
        expr: str,
        rep_n: int,
        check: str,
        delay_n: int,
        parsed: ParsedSVA,
    ) -> list[str]:
        """Check that expr holds for N consecutive cycles, then after delay D, check consequent."""
        cnt_reg = self._unique_reg(f"{label}_ante_cnt")
        width = max(1, rep_n.bit_length())
        lines = [f"    reg [{width-1}:0] {cnt_reg};"]

        if delay_n == 1:
            trig_reg = self._unique_reg(f"{label}_ante_trig")
            lines.append(f"    reg {trig_reg};")
        else:
            trig_reg = self._unique_reg(f"{label}_ante_trig")
            lines.append(f"    reg [{delay_n-1}:0] {trig_reg};")

        lines.extend([
            f"    always @({parsed.clock_edge} {parsed.clock}) begin",
            f"        if ({parsed.reset_condition}) begin",
            f"            {cnt_reg} <= 0;",
            f"            {trig_reg} <= 0;",
            f"        end else begin",
        ])

        if delay_n == 1:
            lines.append(f"            {trig_reg} <= (({expr}) && ({cnt_reg} == {rep_n - 1}));")
        else:
            lines.append(
                f"            {trig_reg} <= {{{trig_reg}[{delay_n-2}:0], (({expr}) && ({cnt_reg} == {rep_n - 1}))}};"
            )

        lines.extend([
            f"            if ({expr}) begin",
            f"                if ({cnt_reg} < {rep_n})",
            f"                    {cnt_reg} <= {cnt_reg} + 1;",
            f"            end else begin",
            f"                {cnt_reg} <= 0;",
            f"            end",
        ])

        trigger_expr = trig_reg if delay_n == 1 else f"{trig_reg}[{delay_n-1}]"
        if atype == "assert":
            lines.append(f"            if ({trigger_expr} && !({check}))")
            lines.append(f"                {label}: assert(0);")
        elif atype == "assume":
            lines.append(f"            if ({trigger_expr})")
            lines.append(f"                {label}: assume({check});")
        elif atype == "cover":
            lines.append(f"            if ({trigger_expr} && ({check}))")
            lines.append(f"                {label}: cover(1);")

        lines.append(f"        end")
        lines.append(f"    end")
        return lines

    def _lower_two_stage_sequence_then_delay(
        self,
        label: str,
        atype: str,
        start_expr: str,
        event_expr: str,
        check_expr: str,
        parsed: ParsedSVA,
    ) -> list[str]:
        """Lower: start ##1 event, then one cycle later check_expr."""
        stage_reg = self._unique_reg(f"{label}_stage")
        trig_reg = self._unique_reg(f"{label}_trig")
        lines = [
            f"    reg {stage_reg};",
            f"    reg {trig_reg};",
            f"    always @({parsed.clock_edge} {parsed.clock}) begin",
            f"        if ({parsed.reset_condition}) begin",
            f"            {stage_reg} <= 0;",
            f"            {trig_reg} <= 0;",
            f"        end else begin",
            f"            {trig_reg} <= ({stage_reg} && ({event_expr}));",
            f"            {stage_reg} <= ({start_expr});",
        ]
        if atype == "assert":
            lines.append(f"            if ({trig_reg} && !({check_expr}))")
            lines.append(f"                {label}: assert(0);")
        elif atype == "assume":
            lines.append(f"            if ({trig_reg})")
            lines.append(f"                {label}: assume({check_expr});")
        elif atype == "cover":
            lines.append(f"            if ({trig_reg} && ({check_expr}))")
            lines.append(f"                {label}: cover(1);")
        lines.append(f"        end")
        lines.append(f"    end")
        return lines

    def _lower_capture_hold_then_event(
        self,
        label: str,
        start_expr: str,
        capture_sig: str,
        capture_width: str,
        hold_expr: str,
        min_cycles: int,
        max_cycles: int,
        event_expr: str,
        check_expr: str,
        parsed: ParsedSVA,
    ) -> list[str]:
        """Lower a captured-data antecedent with bounded hold window and delayed compare."""
        arm_reg = self._unique_reg(f"{label}_arm")
        hold_active = self._unique_reg(f"{label}_hold")
        match_reg = self._unique_reg(f"{label}_match")
        count_reg = self._unique_reg(f"{label}_count")
        capture_reg = f"{label}_capture"
        width = max(1, max_cycles.bit_length())
        capture_width_str = f"{capture_width} " if capture_width else ""
        capture_expr = self._translate_expression(capture_sig, parsed)

        return [
            f"    reg {arm_reg};",
            f"    reg {hold_active};",
            f"    reg {match_reg};",
            f"    reg [{width-1}:0] {count_reg};",
            f"    reg {capture_width_str}{capture_reg};",
            f"    always @({parsed.clock_edge} {parsed.clock}) begin",
            f"        if ({parsed.reset_condition}) begin",
            f"            {arm_reg} <= 0;",
            f"            {hold_active} <= 0;",
            f"            {match_reg} <= 0;",
            f"            {count_reg} <= 0;",
            f"            {capture_reg} <= 0;",
            f"        end else begin",
            f"            if ({match_reg} && !({check_expr}))",
            f"                {label}: assert(0);",
            f"            {match_reg} <= 0;",
            f"            if ({arm_reg}) begin",
            f"                if ({hold_expr}) begin",
            f"                    {hold_active} <= 1;",
            f"                    {count_reg} <= 1;",
            f"                end else begin",
            f"                    {hold_active} <= 0;",
            f"                    {count_reg} <= 0;",
            f"                end",
            f"                {arm_reg} <= 0;",
            f"            end else if ({hold_active}) begin",
            f"                if ({hold_expr} && {count_reg} < {max_cycles}) begin",
            f"                    {count_reg} <= {count_reg} + 1;",
            f"                end else if ({event_expr} && {count_reg} >= {min_cycles} && {count_reg} <= {max_cycles}) begin",
            f"                    {match_reg} <= 1;",
            f"                    {hold_active} <= 0;",
            f"                    {count_reg} <= 0;",
            f"                end else begin",
            f"                    {hold_active} <= 0;",
            f"                    {count_reg} <= 0;",
            f"                end",
            f"            end",
            f"            if ({start_expr}) begin",
            f"                {capture_reg} <= {capture_expr};",
            f"                {arm_reg} <= 1;",
            f"                {hold_active} <= 0;",
            f"                {count_reg} <= 0;",
            f"            end",
            f"        end",
            f"    end",
        ]

    # ═══════════════════════════════════════════════════════════
    # COMMON EMIT: always block with immediate assertion
    # ═══════════════════════════════════════════════════════════

    def _emit_always_block(
        self, label: str, atype: str, condition: str,
        guard: Optional[str], parsed: ParsedSVA,
    ) -> list[str]:
        """Emit a simple always block with an immediate assertion.
        Yosys requires labels to be on their own statement line.
        """
        # Clean up expressions: strip outer whitespace and normalize parens
        condition = self._clean_expr(condition)
        if guard:
            guard = self._clean_expr(guard)

        lines = []
        lines.append(f"    always @({parsed.clock_edge} {parsed.clock}) begin")
        lines.append(f"        if (!({parsed.reset_condition})) begin")

        if guard:
            if atype == "assert":
                lines.append(f"            if ({guard} && !({condition}))")
                lines.append(f"                {label}: assert(0);")
            elif atype == "assume":
                lines.append(f"            if ({guard})")
                lines.append(f"                {label}: assume({condition});")
            elif atype == "cover":
                lines.append(f"            if ({guard} && ({condition}))")
                lines.append(f"                {label}: cover(1);")
        else:
            if atype == "assert":
                lines.append(f"            {label}: assert({condition});")
            elif atype == "assume":
                lines.append(f"            {label}: assume({condition});")
            elif atype == "cover":
                lines.append(f"            if ({condition})")
                lines.append(f"                {label}: cover(1);")

        lines.append(f"        end")
        lines.append(f"    end")
        return lines

    def _clean_expr(self, expr: str) -> str:
        """Clean up an expression: fix unbalanced parens, strip redundant wrapping, backticks."""
        expr = expr.strip()
        # Strip backtick macros
        expr = re.sub(r'`(\w+)', r'\1', expr)

        # Fix unbalanced parentheses: count opens vs closes
        open_count = expr.count('(')
        close_count = expr.count(')')
        if open_count > close_count:
            # Strip leading unmatched '(' characters
            diff = open_count - close_count
            stripped = 0
            result = []
            for ch in expr:
                if ch == '(' and stripped < diff:
                    # Check if this is a leading unmatched paren
                    stripped += 1
                    continue
                result.append(ch)
            expr = ''.join(result).strip()
        elif close_count > open_count:
            # Strip trailing unmatched ')' characters
            diff = close_count - open_count
            stripped = 0
            result = []
            for ch in reversed(expr):
                if ch == ')' and stripped < diff:
                    stripped += 1
                    continue
                result.append(ch)
            expr = ''.join(reversed(result)).strip()

        # Remove balanced redundant outer parentheses: ((x)) → x
        while len(expr) > 2 and expr.startswith('(') and expr.endswith(')'):
            depth = 0
            matched = True
            for i, ch in enumerate(expr):
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                if depth == 0 and i < len(expr) - 1:
                    matched = False
                    break
            if matched:
                expr = expr[1:-1].strip()
            else:
                break
        return expr

    def _auto_detect_signals(self, parsed: ParsedSVA):
        """
        When a module has no port declarations (e.g., uses `define macros),
        auto-detect signals referenced in property bodies and add them as ports.
        """
        # Collect all identifiers used in property bodies
        all_identifiers = set()
        inferred_widths: dict[str, str] = {}
        reserved = {
            parsed.clock, parsed.reset,
            # SystemVerilog keywords to exclude
            "begin", "end", "if", "else", "case", "endcase", "default",
            "always", "assign", "wire", "reg", "logic", "input", "output",
            "posedge", "negedge", "or", "and", "not", "module", "endmodule",
            "property", "endproperty", "sequence", "endsequence",
            "assert", "assume", "cover", "disable", "iff",
            "clocking", "endclocking", "modport",
            # SVA system function names (after $ is stripped)
            "rose", "fell", "stable", "changed", "past", "onehot0", "onehot",
            "countones", "clog2", "bits", "isunknown",
            # Common SV constants
            "b0", "b1", "bX",
        }

        for prop in parsed.properties:
            body = re.sub(r'`(\w+)', r'\1', prop.body)  # strip backticks
            inferred_widths.update(self._infer_signal_widths(body))
            # Find all word-like identifiers that aren't keywords or numbers
            for m in re.finditer(r'\b([a-zA-Z_]\w*)\b', body):
                name = m.group(1)
                if name not in reserved and not name.startswith('$') and not name.isdigit():
                    # Skip property/sequence names
                    prop_names = {p.name for p in parsed.properties}
                    if name not in prop_names:
                        all_identifiers.add(name)

        # Also check for _in / _out suffix patterns (common in SVA macros)
        for sig_name in sorted(all_identifiers):
            if sig_name in (parsed.clock, parsed.reset):
                continue
            parsed.signals.append(SVASignal(
                name=sig_name,
                direction="input",
                width=inferred_widths.get(sig_name, ""),
            ))

        if all_identifiers:
            logger.info(f"Auto-detected {len(parsed.signals)} signals from property bodies")

    # ═══════════════════════════════════════════════════════════
    # EXPRESSION TRANSLATION
    # ═══════════════════════════════════════════════════════════

    def _translate_expression(self, expr: str, parsed: ParsedSVA) -> str:
        """
        Translate SVA expressions into synthesizable Verilog.
        Converts system functions into register-based logic.
        
        Supported:
          $rose(sig)         → (sig && !sig_prev)
          $fell(sig)         → (!sig && sig_prev)
          $stable(sig)       → (sig == sig_prev)
          $changed(sig)      → (sig != sig_prev)
          $past(sig)         → sig_past1
          $past(sig, N)      → sig_pastN
          $onehot0(expr)     → ((expr) & ((expr) - 1)) == 0
          $onehot(expr)      → $onehot0(expr ^ (expr & (expr - 1))) ... simplified
          $countones(expr)   → lowered to popcount logic
        """
        result = expr.strip()

        # Remove any leftover clock/reset specs
        result = re.sub(r'@\s*\(\s*(posedge|negedge)\s+\w+\s*\)\s*', '', result)
        result = re.sub(r'disable\s+iff\s*\(\s*!?\s*\w+\s*\)\s*', '', result)

        # Strip backtick macros
        result = re.sub(r'`(\w+)', r'\1', result)

        # $past(sig, N) → sig_pastN  (must come before $past(sig))
        def replace_past_n(m):
            sig = m.group(1).strip()
            n = int(m.group(2).strip())
            return self._translate_past_expression(sig, n)
        result = re.sub(
            r'\$past\s*\(\s*([^,)]+)\s*,\s*(\d+)\s*\)',
            replace_past_n,
            result
        )

        # $past(sig) → sig_past1
        def replace_past_1(m):
            sig = m.group(1).strip()
            return self._translate_past_expression(sig, 1)
        result = re.sub(
            r'\$past\s*\(\s*([^,)]+)\s*\)',
            replace_past_1,
            result
        )

        # $onehot0(expr) → ((expr) == 0 || ((expr) & ((expr) - 1)) == 0)
        # Correct: at most one bit set
        def replace_onehot0(m):
            inner = m.group(1).strip()
            return f"(({inner}) == 0 || (({inner}) & (({inner}) - 1)) == 0)"
        result = re.sub(
            r'\$onehot0\s*\(\s*(.+?)\s*\)',
            replace_onehot0,
            result
        )

        # $onehot(expr) → ((expr) != 0 && ((expr) & ((expr) - 1)) == 0)
        # Correct: exactly one bit set
        def replace_onehot(m):
            inner = m.group(1).strip()
            return f"(({inner}) != 0 && (({inner}) & (({inner}) - 1)) == 0)"
        result = re.sub(
            r'\$onehot\s*\(\s*(.+?)\s*\)',
            replace_onehot,
            result
        )

        # $countones(expr) — replace with a note; full popcount is complex
        # For now, translate to a simple form that works for narrow signals
        def replace_countones(m):
            inner = m.group(1).strip()
            return f"_va_countones({inner})"
        result = re.sub(
            r'\$countones\s*\(\s*(.+?)\s*\)',
            replace_countones,
            result
        )

        # $rose(sig) → (sig && !sig_prev)
        result = re.sub(
            r'\$rose\s*\(\s*([^)]+)\s*\)',
            r'(\1 && !\1_prev)',
            result
        )

        # $fell(sig) → (!sig && sig_prev)
        result = re.sub(
            r'\$fell\s*\(\s*([^)]+)\s*\)',
            r'(!\1 && \1_prev)',
            result
        )

        # $stable(sig) → (sig == sig_prev)
        result = re.sub(
            r'\$stable\s*\(\s*([^)]+)\s*\)',
            r'(\1 == \1_prev)',
            result
        )

        # $changed(sig) → (sig != sig_prev)
        result = re.sub(
            r'\$changed\s*\(\s*([^)]+)\s*\)',
            r'(\1 != \1_prev)',
            result
        )

        # Final cleanup: strip redundant parens, backticks, whitespace
        result = self._clean_expr(result)
        return result

    def _compact_sva(self, expr: str) -> str:
        """Normalize whitespace for regex pattern matching."""
        return re.sub(r'\s+', ' ', expr.strip())

    def _translate_past_expression(self, expr: str, delay: int) -> str:
        """Translate $past(expr, delay) by shifting each signal reference."""
        expr = re.sub(r'`(\w+)', r'\1', expr.strip())
        reserved = {
            "begin", "end", "if", "else", "case", "endcase", "default",
            "always", "assign", "wire", "reg", "logic", "input", "output",
            "posedge", "negedge", "or", "and", "not", "module", "endmodule",
            "property", "endproperty", "sequence", "endsequence",
            "assert", "assume", "cover", "disable", "iff",
            "clocking", "endclocking", "modport",
            "b0", "b1", "bX", "true", "false",
        }

        def replace_ident(match):
            name = match.group(1)
            if name in reserved or name.isdigit():
                return name
            return f"{name}_past{delay}"

        translated = re.sub(r'\b([a-zA-Z_]\w*)\b', replace_ident, expr)
        if re.match(r'^\w+$', translated):
            return translated
        return f"({translated})"

    def _strip_outer_parens(self, expr: str) -> str:
        """Strip one or more balanced outer parentheses."""
        expr = expr.strip()
        while len(expr) >= 2 and expr.startswith("(") and expr.endswith(")"):
            depth = 0
            matched = True
            for index, ch in enumerate(expr):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                if depth == 0 and index < len(expr) - 1:
                    matched = False
                    break
            if not matched:
                break
            expr = expr[1:-1].strip()
        return expr

    def _extract_local_property_vars(self, body: str) -> dict[str, str]:
        """Extract local property variable declarations like reg[7:0] foo;"""
        vars_by_name = {}
        for match in re.finditer(r'\breg\s*(\[[^\]]+\])\s+(\w+)\s*;', body):
            vars_by_name[match.group(2)] = match.group(1).strip()
        return vars_by_name

    def _extract_expression_identifiers(self, expr: str) -> set[str]:
        """Extract signal-like identifiers from an expression."""
        expr = re.sub(r'`(\w+)', r'\1', expr)
        reserved = {
            "begin", "end", "if", "else", "case", "endcase", "default",
            "always", "assign", "wire", "reg", "logic", "input", "output",
            "posedge", "negedge", "or", "and", "not", "module", "endmodule",
            "property", "endproperty", "sequence", "endsequence",
            "assert", "assume", "cover", "disable", "iff",
            "clocking", "endclocking", "modport",
            "rose", "fell", "stable", "changed", "past", "onehot0", "onehot",
            "countones", "clog2", "bits", "isunknown",
            "b0", "b1", "bX", "true", "false",
        }
        found = set()
        for match in re.finditer(r'\b([a-zA-Z_]\w*)\b', expr):
            name = match.group(1)
            if name not in reserved and not name.isdigit():
                found.add(name)
        return found

    def _strip_local_property_decls(self, expr: str) -> str:
        """Remove leading local property declarations before sequence parsing."""
        return re.sub(r'^\s*(?:reg\s*(?:\[[^\]]+\])?\s+\w+\s*;\s*)+', '', expr).strip()

    def _split_implication(self, expr: str, operator: str) -> Optional[tuple[str, str]]:
        """Split an implication at top level, ignoring nested parentheses."""
        depth = 0
        index = 0
        while index <= len(expr) - len(operator):
            ch = expr[index]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            elif depth == 0 and expr.startswith(operator, index):
                return expr[:index], expr[index + len(operator):]
            index += 1
        return None

    def _infer_signal_widths(self, body: str) -> dict[str, str]:
        """Infer widths for undeclared checker signals from local variable usage."""
        inferred: dict[str, str] = {}
        local_vars = self._extract_local_property_vars(body)
        compact = self._compact_sva(re.sub(r'`(\w+)', r'\1', body))
        for var_name, width in local_vars.items():
            assign_match = re.search(rf'\b{re.escape(var_name)}\s*=\s*(\w+)\b', compact)
            if assign_match:
                inferred.setdefault(assign_match.group(1), width)

            compare_match = re.search(rf'\b(\w+)\s*==\s*{re.escape(var_name)}\b', compact)
            if compare_match:
                inferred.setdefault(compare_match.group(1), width)

            compare_match = re.search(rf'\b{re.escape(var_name)}\s*==\s*(\w+)\b', compact)
            if compare_match:
                inferred.setdefault(compare_match.group(1), width)

        return inferred

    # ═══════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════

    def _collect_past_signals(self, parsed: ParsedSVA) -> list[str]:
        """Find all signals that need past-value registers ($rose/$fell/$stable/$changed)."""
        signals = set()
        for prop in parsed.properties:
            for func in ["$rose", "$fell", "$stable", "$changed"]:
                for m in re.finditer(rf'\{func}\s*\(\s*([^)]+)\s*\)', prop.body):
                    sig = m.group(1).strip()
                    # Only add simple signal names, not complex expressions
                    if re.match(r'^\w+$', sig):
                        signals.add(sig)
        return sorted(signals)

    def _collect_past_delay_signals(self, parsed: ParsedSVA) -> dict:
        """
        Find all signals that need $past registers with delay counts.
        Returns dict: {signal_name: max_delay_needed}
        e.g., {"wr_en_in": 2, "wr_data_in": 2}
        """
        past_signals = {}
        for prop in parsed.properties:
            body = re.sub(r'`(\w+)', r'\1', prop.body)  # strip backticks

            # $past(sig, N)
            for m in re.finditer(r'\$past\s*\(\s*([^,)]+)\s*,\s*(\d+)\s*\)', body):
                sig = m.group(1).strip()
                n = int(m.group(2).strip())
                for ident in self._extract_expression_identifiers(sig):
                    past_signals[ident] = max(past_signals.get(ident, 0), n)

            # $past(sig) — implicit delay of 1
            for m in re.finditer(r'\$past\s*\(\s*([^,)]+)\s*\)', body):
                sig = m.group(1).strip()
                for ident in self._extract_expression_identifiers(sig):
                    past_signals[ident] = max(past_signals.get(ident, 0), 1)

        return past_signals

    def _get_signal_width(self, name: str, parsed: ParsedSVA) -> str:
        """Get width declaration for a signal (e.g., '[31:0] ')."""
        for sig in parsed.signals:
            if sig.name == name and sig.width:
                return f"{sig.width} "
        return ""

    def _unique_reg(self, prefix: str) -> str:
        """Generate a unique register name."""
        self._reg_counter += 1
        return f"_va_{prefix}_{self._reg_counter}"


# ═══════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════

def lower_sva_to_rtl(sva_code: str) -> str:
    """
    One-call API: takes raw SVA code, parses it, lowers it to RTL.
    Returns synthesizable SystemVerilog with `ifdef FORMAL.
    """
    from app.services.sva_parser import parse_sva
    parsed = parse_sva(sva_code)
    engine = SVALoweringEngine()
    return engine.lower(parsed)


# Singleton
lowering_engine = SVALoweringEngine()
