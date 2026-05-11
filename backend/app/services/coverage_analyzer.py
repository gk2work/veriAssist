"""
VeriAssist v2.0 — Coverage Analyzer

Analyzes DUT source code to identify coverage opportunities:
  - FSM state registers and transitions
  - Data path signals with interesting ranges/boundaries
  - Control signal combinations (cross coverage candidates)
  - Protocol-specific coverage patterns
  - Missing corner cases and edge conditions

The analysis drives two downstream features:
  1. Coverage model generation (covergroups with bins)
  2. Sequence recommendations (what to test to close gaps)
"""

import re
import math
import logging
from dataclasses import dataclass, field
from typing import Optional

from app.services.interface_parser import ParsedInterface, Signal

logger = logging.getLogger("veriassist.coverage")


# ═══════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════

@dataclass
class FSMInfo:
    """Detected FSM in the DUT."""
    state_reg: str = ""                    # register name (e.g., "state")
    width: int = 0                         # bit width
    states: list[dict] = field(default_factory=list)  # [{name, value}]
    transitions: list[dict] = field(default_factory=list)  # [{from_state, to_state, condition}]
    reset_state: str = ""
    has_default: bool = False


@dataclass
class CoverageOpportunity:
    """A single coverage opportunity identified in the DUT."""
    category: str = ""       # fsm_state | fsm_transition | data_boundary | control_cross
                             # | protocol_specific | error_path | timing | toggle
    name: str = ""           # human-readable name
    description: str = ""    # what to cover and why
    priority: str = "medium" # high | medium | low
    signals: list[str] = field(default_factory=list)
    coverpoint_hint: str = ""  # suggested coverpoint code snippet
    sequence_hint: str = ""    # suggested sequence to hit this coverage


@dataclass
class CoverageAnalysis:
    """Complete coverage analysis result."""
    module_name: str = ""
    protocol: str = "generic"
    fsms: list[FSMInfo] = field(default_factory=list)
    opportunities: list[CoverageOpportunity] = field(default_factory=list)
    total_opportunities: int = 0
    high_priority: int = 0
    medium_priority: int = 0
    low_priority: int = 0
    analysis_time: float = 0.0

    def get_by_category(self, category: str) -> list[CoverageOpportunity]:
        return [o for o in self.opportunities if o.category == category]

    def get_by_priority(self, priority: str) -> list[CoverageOpportunity]:
        return [o for o in self.opportunities if o.priority == priority]


# ═══════════════════════════════════════════════════════════════
# FSM PATTERNS
# ═══════════════════════════════════════════════════════════════

# Common FSM state register patterns
FSM_REG_PATTERNS = [
    re.compile(r'reg\s+\[(\d+):0\]\s+(state\w*|fsm\w*|cs\w*|ns\w*|current_state|next_state)', re.I),
    re.compile(r'(state\w*|fsm\w*|current_state)\s*<=', re.I),
]

# Localparam/parameter state definitions
STATE_DEF_PATTERNS = [
    re.compile(r'localparam\s+(?:\[\d+:\d+\]\s+)?(\w+)\s*=\s*(\d+\'[bdh][\da-fA-F]+|\d+)', re.I),
    re.compile(r'parameter\s+(?:\[\d+:\d+\]\s+)?(\w+)\s*=\s*(\d+\'[bdh][\da-fA-F]+|\d+)', re.I),
]

# Enum-style state definitions
ENUM_PATTERN = re.compile(
    r'typedef\s+enum\s+(?:logic\s+\[\d+:\d+\]\s+)?'
    r'\{([\s\S]*?)\}\s+(\w+)',
    re.I
)

# Case statement for transitions
CASE_PATTERN = re.compile(r'case\s*\(\s*(\w+)\s*\)', re.I)
CASE_ITEM_PATTERN = re.compile(r'(\w+)\s*:\s*(?:begin\s*)?([\s\S]*?)(?:end\s*$|(?=\w+\s*:)|endcase)', re.I | re.MULTILINE)


# ═══════════════════════════════════════════════════════════════
# MAIN ANALYZER
# ═══════════════════════════════════════════════════════════════

class CoverageAnalyzer:
    """Analyzes DUT code for coverage opportunities."""

    def analyze(
        self,
        dut_code: str,
        iface: Optional[ParsedInterface] = None,
        protocol: str = "",
    ) -> CoverageAnalysis:
        """
        Analyze DUT source code for coverage opportunities.

        Args:
            dut_code: SystemVerilog DUT source code
            iface: Optional parsed interface (for signal classification)
            protocol: Protocol hint for protocol-specific coverage

        Returns:
            CoverageAnalysis with all identified opportunities
        """
        import time
        t0 = time.time()

        result = CoverageAnalysis()
        stripped = self._strip_comments(dut_code)

        # Parse interface if not provided
        if iface:
            result.module_name = iface.module_name
            result.protocol = protocol or iface.protocol
        else:
            m = re.search(r'module\s+(\w+)', stripped)
            result.module_name = m.group(1) if m else "unknown"
            result.protocol = protocol or "generic"

        # 1. Detect FSMs
        result.fsms = self._detect_fsms(stripped)

        # 2. Generate FSM coverage opportunities
        for fsm in result.fsms:
            self._add_fsm_coverage(fsm, result)

        # 3. Generate signal-level coverage opportunities
        if iface:
            self._add_signal_coverage(iface, result)

        # 4. Generate protocol-specific coverage
        if result.protocol != "generic":
            self._add_protocol_coverage(result.protocol, iface, result)

        # 5. Generate timing/corner case coverage
        self._add_corner_case_coverage(stripped, iface, result)

        # 6. Generate toggle coverage opportunities
        if iface:
            self._add_toggle_coverage(iface, result)

        # Compute stats
        result.total_opportunities = len(result.opportunities)
        result.high_priority = len(result.get_by_priority("high"))
        result.medium_priority = len(result.get_by_priority("medium"))
        result.low_priority = len(result.get_by_priority("low"))
        result.analysis_time = time.time() - t0

        logger.info(
            f"Coverage analysis: {result.module_name}, "
            f"{result.total_opportunities} opportunities "
            f"(H:{result.high_priority} M:{result.medium_priority} L:{result.low_priority}), "
            f"{len(result.fsms)} FSMs detected"
        )

        return result

    # ═══════════════════════════════════════════════════════
    # FSM DETECTION
    # ═══════════════════════════════════════════════════════

    def _detect_fsms(self, code: str) -> list[FSMInfo]:
        """Detect FSMs in the DUT code."""
        fsms = []

        # Find state definitions (localparam/parameter)
        state_defs = {}
        for pattern in STATE_DEF_PATTERNS:
            for m in pattern.finditer(code):
                name = m.group(1)
                value = m.group(2)
                # Filter: likely state names are ALL_CAPS or common patterns
                if name.isupper() or any(k in name.lower() for k in ["idle", "init", "done", "start", "wait", "read", "write", "addr", "data", "resp"]):
                    state_defs[name] = value

        # Find enum definitions
        for m in ENUM_PATTERN.finditer(code):
            enum_body = m.group(1)
            for item in re.finditer(r'(\w+)\s*(?:=\s*[\w\']+)?', enum_body):
                state_defs[item.group(1)] = item.group(1)

        if not state_defs:
            return fsms

        # Find case statements that use these states
        for cm in CASE_PATTERN.finditer(code):
            case_var = cm.group(1)

            # Check if case variable matches any state-related register
            is_state = any(k in case_var.lower() for k in ["state", "fsm", "cs", "ns"])
            if not is_state:
                # Check if case items use our detected state names
                case_start = cm.end()
                case_end = code.find("endcase", case_start)
                if case_end < 0:
                    continue
                case_body = code[case_start:case_end]
                matching = sum(1 for s in state_defs if s in case_body)
                if matching < 2:
                    continue

            fsm = FSMInfo(state_reg=case_var)

            # Detect width
            width_match = re.search(rf'(?:reg|logic)\s+\[(\d+):0\]\s+{re.escape(case_var)}', code)
            if width_match:
                fsm.width = int(width_match.group(1)) + 1
            else:
                fsm.width = max(3, math.ceil(math.log2(max(len(state_defs), 2))))

            # Add states
            for sname, sval in state_defs.items():
                fsm.states.append({"name": sname, "value": str(sval)})

            # Detect transitions from case body
            case_start = cm.end()
            case_end = code.find("endcase", case_start)
            if case_end > 0:
                case_body = code[case_start:case_end]
                fsm.has_default = "default" in case_body

                # Extract transitions: state_name: ... next_state <= OTHER_STATE
                for sname in state_defs:
                    # Find what this state transitions to
                    state_section = re.search(
                        rf'{re.escape(sname)}\s*:\s*([\s\S]*?)(?=\b(?:{"|".join(re.escape(s) for s in state_defs)})\s*:|default\s*:|endcase)',
                        case_body
                    )
                    if state_section:
                        section = state_section.group(1)
                        # Find assignments to state register
                        for target in re.finditer(rf'{re.escape(case_var)}\s*<=\s*(\w+)', section):
                            to_state = target.group(1)
                            if to_state in state_defs or to_state == sname:
                                # Try to find condition
                                condition = ""
                                cond_match = re.search(r'if\s*\((.*?)\)', section[:target.start()])
                                if cond_match:
                                    condition = cond_match.group(1).strip()

                                fsm.transitions.append({
                                    "from_state": sname,
                                    "to_state": to_state,
                                    "condition": condition,
                                })

            # Detect reset state
            reset_match = re.search(rf'{re.escape(case_var)}\s*<=\s*(\w+)\s*;', code[:cm.start()])
            if reset_match and reset_match.group(1) in state_defs:
                fsm.reset_state = reset_match.group(1)

            if fsm.states:
                fsms.append(fsm)

        return fsms

    # ═══════════════════════════════════════════════════════
    # COVERAGE OPPORTUNITY GENERATION
    # ═══════════════════════════════════════════════════════

    def _add_fsm_coverage(self, fsm: FSMInfo, result: CoverageAnalysis):
        """Generate FSM-related coverage opportunities."""

        # State coverage — every state must be visited
        result.opportunities.append(CoverageOpportunity(
            category="fsm_state",
            name=f"FSM state coverage ({fsm.state_reg})",
            description=f"Cover all {len(fsm.states)} states of FSM '{fsm.state_reg}': {', '.join(s['name'] for s in fsm.states)}",
            priority="high",
            signals=[fsm.state_reg],
            coverpoint_hint=f"coverpoint {fsm.state_reg} {{\n" +
                "\n".join(f"    bins {s['name']} = {{{s['value']}}};" for s in fsm.states) +
                "\n}",
        ))

        # Transition coverage — every valid transition must be exercised
        if fsm.transitions:
            transitions_str = ", ".join(f"{t['from_state']}->{t['to_state']}" for t in fsm.transitions)
            result.opportunities.append(CoverageOpportunity(
                category="fsm_transition",
                name=f"FSM transition coverage ({fsm.state_reg})",
                description=f"Cover all {len(fsm.transitions)} transitions: {transitions_str}",
                priority="high",
                signals=[fsm.state_reg],
                coverpoint_hint=f"coverpoint {fsm.state_reg} {{\n" +
                    "    bins transitions[] = (" +
                    " => ".join(sorted(set(t['from_state'] for t in fsm.transitions))) +
                    ");\n}",
            ))

        # Illegal state coverage
        if not fsm.has_default:
            max_states = 2 ** fsm.width
            defined = len(fsm.states)
            if defined < max_states:
                result.opportunities.append(CoverageOpportunity(
                    category="fsm_state",
                    name=f"FSM illegal state check ({fsm.state_reg})",
                    description=f"FSM has {defined} defined states but {fsm.width}-bit register allows {max_states}. "
                                f"Missing 'default' case — states {defined}-{max_states-1} are unreachable but should be covered as illegal.",
                    priority="high",
                    signals=[fsm.state_reg],
                    coverpoint_hint=f"coverpoint {fsm.state_reg} {{\n"
                        f"    illegal_bins illegal = {{[{defined}:{max_states-1}]}};\n}}",
                    sequence_hint="Add SVA assertion: state must always be in valid range. Use formal verification to prove.",
                ))

        # Reset state coverage
        if fsm.reset_state:
            result.opportunities.append(CoverageOpportunity(
                category="fsm_state",
                name=f"FSM reset recovery ({fsm.state_reg})",
                description=f"After reset, FSM must be in {fsm.reset_state}. Cover the reset-to-first-transition path.",
                priority="medium",
                signals=[fsm.state_reg],
                sequence_hint=f"Apply reset, then immediately start a transaction to exercise {fsm.reset_state} exit path.",
            ))

    def _add_signal_coverage(self, iface: ParsedInterface, result: CoverageAnalysis):
        """Generate signal-level coverage opportunities."""

        # Data boundary coverage
        for sig in iface.data_signals:
            if sig.width > 1:
                result.opportunities.append(CoverageOpportunity(
                    category="data_boundary",
                    name=f"Data boundary ({sig.name})",
                    description=f"Cover boundary values of {sig.width}-bit signal '{sig.name}': min (0), max ({2**sig.width-1}), mid ({2**(sig.width-1)})",
                    priority="medium",
                    signals=[sig.name],
                    coverpoint_hint=f"coverpoint {sig.name} {{\n"
                        f"    bins zero = {{0}};\n"
                        f"    bins max_val = {{{2**sig.width-1}}};\n"
                        f"    bins mid = {{{2**(sig.width-1)}}};\n"
                        f"    bins others = default;\n}}",
                    sequence_hint=f"Generate transactions with {sig.name} = 0, {2**sig.width-1}, and {2**(sig.width-1)}",
                ))

        # Control signal cross coverage
        ctrl_inputs = [s for s in iface.control_signals if s.direction == "input"]
        if len(ctrl_inputs) >= 2:
            names = [s.name for s in ctrl_inputs[:4]]  # limit to 4 for manageable cross
            result.opportunities.append(CoverageOpportunity(
                category="control_cross",
                name=f"Control signal cross ({', '.join(names)})",
                description=f"Cross coverage of control signals: all combinations of {', '.join(names)}",
                priority="high",
                signals=names,
                coverpoint_hint=f"cross " + ", ".join(f"cp_{n}" for n in names) + ";",
                sequence_hint=f"Generate sequences that exercise all combinations of {', '.join(names)} being 0/1",
            ))

        # Address alignment coverage
        for sig in iface.address_signals:
            if sig.width >= 4:
                result.opportunities.append(CoverageOpportunity(
                    category="data_boundary",
                    name=f"Address alignment ({sig.name})",
                    description=f"Cover aligned and unaligned addresses for {sig.width}-bit address '{sig.name}'",
                    priority="medium",
                    signals=[sig.name],
                    coverpoint_hint=f"coverpoint {sig.name}[1:0] {{\n"
                        f"    bins aligned = {{0}};\n"
                        f"    bins unaligned = {{1, 2, 3}};\n}}",
                ))

    def _add_protocol_coverage(self, protocol: str, iface: Optional[ParsedInterface], result: CoverageAnalysis):
        """Add protocol-specific coverage opportunities."""

        if protocol in ("axi", "axi_lite"):
            result.opportunities.extend([
                CoverageOpportunity(
                    category="protocol_specific",
                    name="AXI write-read ordering",
                    description="Cover write followed by read to same address, read followed by write, and simultaneous write+read channels",
                    priority="high",
                    signals=["awvalid", "arvalid"],
                    sequence_hint="Generate sequences: write-then-read, read-then-write, and simultaneous AW+AR channel activity",
                ),
                CoverageOpportunity(
                    category="protocol_specific",
                    name="AXI response types",
                    description="Cover all BRESP and RRESP values: OKAY (00), EXOKAY (01), SLVERR (10), DECERR (11)",
                    priority="high",
                    signals=["bresp", "rresp"],
                    coverpoint_hint="coverpoint bresp { bins okay = {0}; bins exokay = {1}; bins slverr = {2}; bins decerr = {3}; }",
                ),
                CoverageOpportunity(
                    category="protocol_specific",
                    name="AXI back-to-back transactions",
                    description="Cover consecutive transactions without idle cycles between them",
                    priority="medium",
                    signals=["awvalid", "awready"],
                    sequence_hint="Generate back-to-back write sequences with no gaps between handshakes",
                ),
                CoverageOpportunity(
                    category="protocol_specific",
                    name="AXI ready-before-valid",
                    description="Cover the case where READY is asserted before VALID (early ready)",
                    priority="medium",
                    signals=["awvalid", "awready"],
                    sequence_hint="Configure slave model to assert AWREADY before master asserts AWVALID",
                ),
            ])

        elif protocol == "apb":
            result.opportunities.extend([
                CoverageOpportunity(
                    category="protocol_specific",
                    name="APB wait states",
                    description="Cover 0, 1, 2, and maximum wait states (PREADY delayed)",
                    priority="high",
                    signals=["pready", "penable"],
                    sequence_hint="Configure slave to respond with varying PREADY delays: 0, 1, 2, max cycles",
                ),
                CoverageOpportunity(
                    category="protocol_specific",
                    name="APB error response",
                    description="Cover PSLVERR assertion during access phase",
                    priority="medium",
                    signals=["pslverr"],
                    sequence_hint="Configure slave to return PSLVERR=1 for specific address ranges",
                ),
            ])

        elif protocol == "fifo":
            result.opportunities.extend([
                CoverageOpportunity(
                    category="protocol_specific",
                    name="FIFO fill levels",
                    description="Cover empty, 1 item, half-full, almost-full, and full states",
                    priority="high",
                    signals=["full", "empty", "count"],
                    coverpoint_hint="coverpoint count {\n"
                        "    bins empty = {0};\n    bins one = {1};\n"
                        "    bins half = {DEPTH/2};\n    bins almost_full = {DEPTH-1};\n"
                        "    bins full = {DEPTH};\n}",
                    sequence_hint="Write items to reach each fill level, then verify flags",
                ),
                CoverageOpportunity(
                    category="protocol_specific",
                    name="FIFO simultaneous read/write",
                    description="Cover simultaneous read and write at various fill levels",
                    priority="high",
                    signals=["wr_en", "rd_en"],
                    coverpoint_hint="cross cp_wr_en, cp_rd_en, cp_fill_level;",
                    sequence_hint="Assert both wr_en and rd_en simultaneously at empty, half-full, and full states",
                ),
                CoverageOpportunity(
                    category="protocol_specific",
                    name="FIFO overflow attempt",
                    description="Cover write attempt when FIFO is full (should be blocked)",
                    priority="high",
                    signals=["wr_en", "full"],
                    sequence_hint="Fill FIFO completely, then attempt additional writes",
                ),
            ])

        elif protocol == "spi":
            result.opportunities.extend([
                CoverageOpportunity(
                    category="protocol_specific",
                    name="SPI data patterns",
                    description="Cover all-zeros, all-ones, alternating patterns (0xAA, 0x55) on MOSI/MISO",
                    priority="medium",
                    signals=["mosi", "miso", "tx_data"],
                    sequence_hint="Send data patterns: 0x00, 0xFF, 0xAA, 0x55, and random values",
                ),
            ])

    def _add_corner_case_coverage(self, code: str, iface: Optional[ParsedInterface], result: CoverageAnalysis):
        """Identify corner case coverage opportunities from code structure."""

        # Back-to-back reset
        result.opportunities.append(CoverageOpportunity(
            category="timing",
            name="Reset during operation",
            description="Apply reset while a transaction is in progress (mid-operation reset)",
            priority="medium",
            signals=["rst_n"] if iface else [],
            sequence_hint="Start a transaction, then assert reset before it completes. Verify clean recovery.",
        ))

        # Consecutive identical transactions
        if iface and iface.data_signals:
            result.opportunities.append(CoverageOpportunity(
                category="timing",
                name="Consecutive identical transactions",
                description="Send the same transaction data twice in a row to test data path stickiness",
                priority="low",
                signals=[s.name for s in iface.data_signals[:2]],
                sequence_hint="Generate two identical transactions back-to-back with same address and data",
            ))

    def _add_toggle_coverage(self, iface: ParsedInterface, result: CoverageAnalysis):
        """Add toggle coverage for key signals."""
        key_signals = iface.control_signals + iface.data_signals[:3]
        if key_signals:
            result.opportunities.append(CoverageOpportunity(
                category="toggle",
                name="Signal toggle coverage",
                description=f"Verify all bits of key signals toggle 0->1 and 1->0: {', '.join(s.name for s in key_signals[:6])}",
                priority="low",
                signals=[s.name for s in key_signals[:6]],
                sequence_hint="Run random sequences long enough to toggle all bits of data and control signals",
            ))

    def _strip_comments(self, code: str) -> str:
        code = re.sub(r'/\*[\s\S]*?\*/', '', code)
        code = re.sub(r'//.*$', '', code, flags=re.MULTILINE)
        return code


# ═══════════════════════════════════════════════════════════════
# UTILITY
# ═══════════════════════════════════════════════════════════════

def format_analysis_summary(analysis: CoverageAnalysis) -> str:
    """Human-readable coverage analysis summary."""
    lines = [
        f"Coverage Analysis: {analysis.module_name} ({analysis.protocol})",
        f"FSMs detected: {len(analysis.fsms)}",
        f"Coverage opportunities: {analysis.total_opportunities}",
        f"  High priority: {analysis.high_priority}",
        f"  Medium priority: {analysis.medium_priority}",
        f"  Low priority: {analysis.low_priority}",
        "",
    ]

    for fsm in analysis.fsms:
        lines.append(f"FSM '{fsm.state_reg}': {len(fsm.states)} states, {len(fsm.transitions)} transitions")
        for s in fsm.states:
            lines.append(f"  {s['name']} = {s['value']}")

    lines.append("")
    for cat in ["fsm_state", "fsm_transition", "data_boundary", "control_cross", "protocol_specific", "timing", "toggle"]:
        opps = analysis.get_by_category(cat)
        if opps:
            lines.append(f"[{cat}]")
            for o in opps:
                lines.append(f"  [{o.priority.upper()}] {o.name}: {o.description[:80]}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════

coverage_analyzer = CoverageAnalyzer()