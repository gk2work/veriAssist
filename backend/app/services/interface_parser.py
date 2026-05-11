"""
VeriAssist v2.0 — Interface Parser

Parses DUT source code or user-provided signal descriptions into
a structured interface representation used by the UVM generator.

Supports:
- DUT SystemVerilog source code parsing (module port extraction)
- User-provided signal list (name, width, direction)
- Protocol detection (AXI, APB, SPI, UART, FIFO, generic)
- Clock/reset identification
- Interface grouping (control, data, address, status signals)

The parsed interface drives the entire UVM testbench generation:
- Transaction fields come from the signal list
- Driver timing comes from the protocol
- Monitor sampling comes from the signal directions
- Coverage bins come from the signal widths and types
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("veriassist.interface_parser")


# ═══════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════

@dataclass
class Signal:
    """A single signal in the interface."""
    name: str
    width: int = 1
    direction: str = "input"       # input | output | inout
    msb: int = 0
    lsb: int = 0
    is_clock: bool = False
    is_reset: bool = False
    group: str = "data"            # clock | reset | control | address | data | status | strobe
    description: str = ""


@dataclass
class ParsedInterface:
    """Complete parsed interface description."""
    module_name: str = ""
    clock: str = "clk"
    reset: str = "rst_n"
    reset_active_low: bool = True
    signals: list[Signal] = field(default_factory=list)
    protocol: str = "generic"      # axi | axi_lite | apb | spi | uart | fifo | wishbone | generic
    parameters: dict = field(default_factory=dict)
    raw_code: str = ""

    @property
    def input_signals(self) -> list[Signal]:
        """Signals driven by the testbench (DUT inputs)."""
        return [s for s in self.signals if s.direction == "input" and not s.is_clock and not s.is_reset]

    @property
    def output_signals(self) -> list[Signal]:
        """Signals observed by the testbench (DUT outputs)."""
        return [s for s in self.signals if s.direction == "output"]

    @property
    def data_signals(self) -> list[Signal]:
        """Data-path signals (typically wide, need constraints)."""
        return [s for s in self.signals if s.group == "data"]

    @property
    def control_signals(self) -> list[Signal]:
        """Control signals (typically 1-bit enables, valids, readys)."""
        return [s for s in self.signals if s.group == "control"]

    @property
    def address_signals(self) -> list[Signal]:
        """Address signals."""
        return [s for s in self.signals if s.group == "address"]

    def get_signal(self, name: str) -> Optional[Signal]:
        """Find signal by name."""
        for s in self.signals:
            if s.name == name:
                return s
        return None

    @property
    def max_data_width(self) -> int:
        """Widest data signal — used for transaction field sizing."""
        widths = [s.width for s in self.data_signals]
        return max(widths) if widths else 32

    @property
    def has_handshake(self) -> bool:
        """Does the interface have valid/ready handshake signals?"""
        names = {s.name.lower() for s in self.signals}
        return bool(
            ({"valid", "ready"} & names) or
            any("valid" in n and "ready" in n.replace("valid", "ready") for n in names)
        )


# ═══════════════════════════════════════════════════════════════
# PROTOCOL DETECTION PATTERNS
# ═══════════════════════════════════════════════════════════════

PROTOCOL_PATTERNS = {
    "axi": {
        "required": ["awvalid", "awready"],
        "optional": ["wvalid", "wready", "bvalid", "bready", "arvalid", "arready", "rvalid", "rready"],
        "keywords": ["awaddr", "wdata", "bresp", "araddr", "rdata", "rresp", "awlen", "awsize", "awburst"],
    },
    "axi_lite": {
        "required": ["awvalid", "awready"],
        "optional": ["wvalid", "wready", "bvalid", "bready", "arvalid", "arready", "rvalid", "rready"],
        "keywords": ["awaddr", "wdata", "bresp", "araddr", "rdata", "rresp"],
        "exclude": ["awlen", "awsize", "awburst", "awcache"],
    },
    "apb": {
        "required": ["psel", "penable"],
        "optional": ["pready", "pslverr"],
        "keywords": ["paddr", "pwdata", "prdata", "pwrite", "pstrb"],
    },
    "spi": {
        "required": ["sclk", "mosi"],
        "optional": ["miso", "cs_n", "ss_n"],
        "keywords": ["cpol", "cpha"],
    },
    "uart": {
        "required": ["tx"],
        "optional": ["rx", "cts", "rts"],
        "keywords": ["baud", "parity"],
    },
    "fifo": {
        "required": ["wr_en", "rd_en"],
        "optional": ["full", "empty"],
        "keywords": ["wr_data", "rd_data", "count", "almost_full", "almost_empty"],
    },
    "wishbone": {
        "required": ["cyc", "stb"],
        "optional": ["ack", "err", "rty"],
        "keywords": ["adr", "dat_i", "dat_o", "we", "sel"],
    },
}

# Signal classification patterns
CLOCK_PATTERNS = re.compile(r'^(clk|clock|sys_clk|aclk|pclk|sclk|hclk|fclk)\w*$', re.IGNORECASE)
RESET_PATTERNS = re.compile(r'^(rst|reset|rstn|rst_n|areset|aresetn|preset|presetn)\w*$', re.IGNORECASE)

SIGNAL_GROUP_RULES = [
    # (pattern, group)
    (re.compile(r'(addr|adr)\w*', re.I), "address"),
    (re.compile(r'(data|dat_|wdata|rdata|wr_data|rd_data|din|dout|d_in|d_out)\w*', re.I), "data"),
    (re.compile(r'(valid|ready|en|enable|wr_en|rd_en|we|re|start|done|busy|ack|grant|req|sel|stb|cyc)\w*', re.I), "control"),
    (re.compile(r'(strb|wstrb|be|byte_en)\w*', re.I), "strobe"),
    (re.compile(r'(full|empty|almost|count|level|status|err|error|resp|slverr|overflow|underflow)\w*', re.I), "status"),
]


# ═══════════════════════════════════════════════════════════════
# MAIN PARSER
# ═══════════════════════════════════════════════════════════════

def parse_interface(
    dut_code: str = "",
    signal_list: list[dict] = None,
    module_name: str = "",
    protocol_hint: str = "",
) -> ParsedInterface:
    """
    Parse a DUT interface from source code or a signal list.

    Args:
        dut_code: SystemVerilog source code of the DUT
        signal_list: Manual signal list [{"name": "awvalid", "width": 1, "direction": "input"}, ...]
        module_name: Override module name (auto-detected from code if empty)
        protocol_hint: Override protocol detection ("axi", "apb", etc.)

    Returns:
        ParsedInterface with all signals classified and protocol detected
    """
    result = ParsedInterface(raw_code=dut_code)

    # Parse signals from source code or signal list
    if dut_code:
        _parse_from_code(dut_code, result)
    elif signal_list:
        _parse_from_list(signal_list, result)

    # Override module name if provided
    if module_name:
        result.module_name = module_name

    # Identify clock and reset
    _identify_clock_reset(result)

    # Classify signals into groups
    _classify_signals(result)

    # Detect protocol
    if protocol_hint:
        result.protocol = protocol_hint.lower()
    else:
        result.protocol = _detect_protocol(result)

    logger.info(
        f"Parsed interface: module={result.module_name}, "
        f"protocol={result.protocol}, "
        f"signals={len(result.signals)} "
        f"(in={len(result.input_signals)}, out={len(result.output_signals)}), "
        f"clk={result.clock}, rst={result.reset}"
    )

    return result


# ═══════════════════════════════════════════════════════════════
# PARSING FROM SOURCE CODE
# ═══════════════════════════════════════════════════════════════

def _parse_from_code(code: str, result: ParsedInterface):
    """Extract module name, parameters, and ports from SystemVerilog code."""
    stripped = re.sub(r'//.*$', '', code, flags=re.MULTILINE)
    stripped = re.sub(r'/\*[\s\S]*?\*/', '', stripped)

    # Module name
    m = re.search(r'module\s+(\w+)', stripped)
    if m:
        result.module_name = m.group(1)

    # Parameters
    param_match = re.search(r'#\s*\(([\s\S]*?)\)\s*\(', stripped)
    if param_match:
        param_text = param_match.group(1)
        for pm in re.finditer(r'parameter\s+(?:\w+\s+)?(\w+)\s*=\s*(\w+)', param_text):
            result.parameters[pm.group(1)] = pm.group(2)

    # Port list — handle parameterized modules
    port_match = re.search(
        r'module\s+\w+\s*(?:#\s*\([\s\S]*?\)\s*)?\(([\s\S]*?)\)\s*;',
        stripped
    )
    if not port_match:
        return

    port_text = port_match.group(1)

    # Parse ports — handle complex widths like [$clog2(DEPTH):0]
    port_pattern = re.compile(
        r'(input|output|inout)\s+'
        r'(?:(wire|logic|reg)\s+)?'
        r'(?:signed\s+)?'
        r'(\[[\s\S]*?\]\s+)?'
        r'(\w+)'
    )

    for pm in port_pattern.finditer(port_text):
        direction = pm.group(1)
        width_str = pm.group(3).strip() if pm.group(3) else ""
        name = pm.group(4)

        # Parse width
        width = 1
        msb = 0
        lsb = 0
        if width_str:
            w = _parse_width(width_str, result.parameters)
            width = w["width"]
            msb = w["msb"]
            lsb = w["lsb"]

        result.signals.append(Signal(
            name=name,
            width=width,
            direction=direction,
            msb=msb,
            lsb=lsb,
        ))


def _parse_width(width_str: str, params: dict) -> dict:
    """Parse a width specification like [31:0], [WIDTH-1:0], [$clog2(DEPTH):0]."""
    width_str = width_str.strip("[] ")

    # Try simple numeric: [31:0]
    m = re.match(r'(\d+)\s*:\s*(\d+)', width_str)
    if m:
        msb = int(m.group(1))
        lsb = int(m.group(2))
        return {"width": abs(msb - lsb) + 1, "msb": msb, "lsb": lsb}

    # Try parameter-based: [WIDTH-1:0]
    m = re.match(r'(\w+)\s*-\s*1\s*:\s*0', width_str)
    if m:
        param_name = m.group(1)
        if param_name in params:
            try:
                val = int(params[param_name])
                return {"width": val, "msb": val - 1, "lsb": 0}
            except ValueError:
                pass
        return {"width": 8, "msb": 7, "lsb": 0}  # default

    # Try $clog2: [$clog2(DEPTH):0]
    m = re.match(r'\$clog2\s*\(\s*(\w+)\s*\)\s*:\s*0', width_str)
    if m:
        param_name = m.group(1)
        if param_name in params:
            try:
                val = int(params[param_name])
                import math
                clog2 = max(1, math.ceil(math.log2(val))) if val > 0 else 1
                return {"width": clog2 + 1, "msb": clog2, "lsb": 0}
            except (ValueError, TypeError):
                pass
        return {"width": 4, "msb": 3, "lsb": 0}  # default for $clog2

    # Fallback
    return {"width": 8, "msb": 7, "lsb": 0}


# ═══════════════════════════════════════════════════════════════
# PARSING FROM SIGNAL LIST
# ═══════════════════════════════════════════════════════════════

def _parse_from_list(signal_list: list[dict], result: ParsedInterface):
    """Parse from a user-provided signal list."""
    for sig_dict in signal_list:
        name = sig_dict.get("name", "")
        if not name:
            continue

        width = sig_dict.get("width", 1)
        direction = sig_dict.get("direction", "input")
        msb = width - 1 if width > 1 else 0

        result.signals.append(Signal(
            name=name,
            width=width,
            direction=direction,
            msb=msb,
            lsb=0,
            description=sig_dict.get("description", ""),
        ))


# ═══════════════════════════════════════════════════════════════
# SIGNAL CLASSIFICATION
# ═══════════════════════════════════════════════════════════════

def _identify_clock_reset(result: ParsedInterface):
    """Identify clock and reset signals."""
    for sig in result.signals:
        if CLOCK_PATTERNS.match(sig.name):
            sig.is_clock = True
            sig.group = "clock"
            result.clock = sig.name

        elif RESET_PATTERNS.match(sig.name):
            sig.is_reset = True
            sig.group = "reset"
            result.reset = sig.name
            result.reset_active_low = "n" in sig.name.lower() or sig.name.lower().endswith("_n")


def _classify_signals(result: ParsedInterface):
    """Classify each signal into a functional group."""
    for sig in result.signals:
        if sig.is_clock or sig.is_reset:
            continue

        # Try pattern matching
        classified = False
        for pattern, group in SIGNAL_GROUP_RULES:
            if pattern.match(sig.name):
                sig.group = group
                classified = True
                break

        if not classified:
            # Heuristic: wide signals (>1 bit) are likely data
            if sig.width > 1:
                sig.group = "data"
            else:
                sig.group = "control"


def _detect_protocol(result: ParsedInterface) -> str:
    """Detect the interface protocol from signal names."""
    signal_names = {s.name.lower() for s in result.signals}

    best_match = "generic"
    best_score = 0

    for proto_name, patterns in PROTOCOL_PATTERNS.items():
        score = 0

        # Check required signals
        required = patterns.get("required", [])
        required_match = sum(1 for r in required if r.lower() in signal_names)
        if required_match < len(required):
            continue  # skip if not all required signals present

        score += required_match * 3

        # Check optional signals
        optional = patterns.get("optional", [])
        score += sum(1 for o in optional if o.lower() in signal_names) * 2

        # Check keyword signals
        keywords = patterns.get("keywords", [])
        score += sum(1 for k in keywords if k.lower() in signal_names)

        # Check exclusions (e.g., AXI-Lite excludes burst signals)
        exclude = patterns.get("exclude", [])
        if exclude and any(e.lower() in signal_names for e in exclude):
            if proto_name == "axi_lite":
                continue  # has burst signals — it's full AXI, not lite

        if score > best_score:
            best_score = score
            best_match = proto_name

    return best_match


# ═══════════════════════════════════════════════════════════════
# UTILITY
# ═══════════════════════════════════════════════════════════════

def format_interface_summary(iface: ParsedInterface) -> str:
    """Human-readable interface summary."""
    lines = [
        f"Module: {iface.module_name}",
        f"Protocol: {iface.protocol}",
        f"Clock: {iface.clock}",
        f"Reset: {iface.reset} (active {'low' if iface.reset_active_low else 'high'})",
        f"Parameters: {iface.parameters}" if iface.parameters else "",
        "",
        f"Signals ({len(iface.signals)}):",
    ]

    groups = {}
    for sig in iface.signals:
        groups.setdefault(sig.group, []).append(sig)

    for group in ["clock", "reset", "control", "address", "data", "strobe", "status"]:
        sigs = groups.get(group, [])
        if sigs:
            lines.append(f"  {group}:")
            for s in sigs:
                width_str = f"[{s.msb}:{s.lsb}]" if s.width > 1 else "     "
                lines.append(f"    {s.direction:6s} {width_str:8s} {s.name}")

    return "\n".join(l for l in lines if l is not None)


def interface_to_dict(iface: ParsedInterface) -> dict:
    """Convert to serializable dict for API responses."""
    return {
        "module_name": iface.module_name,
        "protocol": iface.protocol,
        "clock": iface.clock,
        "reset": iface.reset,
        "reset_active_low": iface.reset_active_low,
        "parameters": iface.parameters,
        "signal_count": len(iface.signals),
        "input_count": len(iface.input_signals),
        "output_count": len(iface.output_signals),
        "has_handshake": iface.has_handshake,
        "max_data_width": iface.max_data_width,
        "signals": [
            {
                "name": s.name,
                "width": s.width,
                "direction": s.direction,
                "msb": s.msb,
                "lsb": s.lsb,
                "group": s.group,
                "is_clock": s.is_clock,
                "is_reset": s.is_reset,
            }
            for s in iface.signals
        ],
    }