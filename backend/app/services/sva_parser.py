"""
VeriAssist v2.0 — SVA Parser

Parses LLM-generated SVA checker modules into a structured representation
that the lowering engine can consume.

Input: SystemVerilog text containing a checker module with properties,
       sequences, assertions, default clocking, disable iff.

Output: ParsedSVA dataclass containing all extracted elements.

This parser is designed for LLM-generated code that follows the VeriAssist
Formal mode template — it handles the specific patterns our prompts produce.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("veriassist.sva_parser")


# ═══════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════

@dataclass
class SVASignal:
    """A signal port from the checker module."""
    name: str
    direction: str = "input"  # input | output
    width: str = ""           # e.g., "[31:0]" or "" for 1-bit
    type: str = "logic"       # logic | wire | reg


@dataclass
class SVASequence:
    """A named sequence definition."""
    name: str
    body: str                 # raw SVA sequence body
    params: list[str] = field(default_factory=list)


@dataclass
class SVAProperty:
    """A named property definition."""
    name: str
    body: str                 # raw SVA property body (temporal logic)
    clock: str = ""           # clock if specified inline (overrides default)
    reset: str = ""           # reset if specified inline (overrides default)
    params: list[str] = field(default_factory=list)


@dataclass
class SVAAssertion:
    """An assert/assume/cover property statement."""
    label: str                # assertion label (e.g., assert_awvalid_stable)
    type: str                 # "assert" | "assume" | "cover"
    property_name: str        # referenced property name
    inline_body: str = ""     # if inline (no named property reference)


@dataclass
class ParsedSVA:
    """Complete parsed representation of an SVA checker module."""
    module_name: str = ""
    clock: str = "clk"
    clock_edge: str = "posedge"
    reset: str = "rst_n"
    reset_active_low: bool = True
    signals: list[SVASignal] = field(default_factory=list)
    sequences: list[SVASequence] = field(default_factory=list)
    properties: list[SVAProperty] = field(default_factory=list)
    assertions: list[SVAAssertion] = field(default_factory=list)
    raw_code: str = ""
    bind_statement: str = ""

    def get_property(self, name: str) -> Optional[SVAProperty]:
        """Find a property by name."""
        for p in self.properties:
            if p.name == name:
                return p
        return None

    def get_all_signal_names(self) -> list[str]:
        """Return all signal names excluding clock and reset."""
        return [s.name for s in self.signals if s.name not in (self.clock, self.reset)]

    @property
    def reset_condition(self) -> str:
        """Return the reset condition as used in RTL (active high)."""
        if self.reset_active_low:
            return f"!{self.reset}"
        return self.reset


# ═══════════════════════════════════════════════════════════════
# PARSER
# ═══════════════════════════════════════════════════════════════

def parse_sva(code: str) -> ParsedSVA:
    """
    Parse SVA checker module code into structured representation.

    Handles:
    - module declaration with ports
    - default clocking / default disable iff
    - named sequences (sequence ... endsequence)
    - named properties (property ... endproperty)
    - assert/assume/cover property statements
    - parameterized properties
    - bind statements
    """
    result = ParsedSVA(raw_code=code)

    # Strip comments for parsing
    stripped = _strip_comments(code)

    # Preprocess: strip backtick macros (`name → name) so regex can match signal names
    preprocessed = re.sub(r'`(\w+)', r'\1', stripped)

    # 1. Extract module name
    _parse_module_name(preprocessed, result)

    # 2. Extract ports/signals
    _parse_signals(preprocessed, result)

    # 3. Extract default clocking
    _parse_default_clocking(preprocessed, result)

    # 4. Extract default disable iff
    _parse_default_disable(preprocessed, result)

    # 5. Extract named sequences
    _parse_sequences(preprocessed, result)

    # 6. Extract named properties
    _parse_properties(preprocessed, result)

    # 7. Extract assertions (assert/assume/cover)
    _parse_assertions(preprocessed, result)

    # 8. Extract bind statement
    _parse_bind(code, result)  # use original code (bind may be outside module)

    logger.info(
        f"Parsed SVA: module={result.module_name}, "
        f"clk={result.clock}({result.clock_edge}), rst={result.reset}, "
        f"signals={len(result.signals)}, properties={len(result.properties)}, "
        f"assertions={len(result.assertions)}"
    )

    return result


# ═══════════════════════════════════════════════════════════════
# PARSING HELPERS
# ═══════════════════════════════════════════════════════════════

def _strip_comments(code: str) -> str:
    """Remove // and /* */ comments."""
    code = re.sub(r'/\*[\s\S]*?\*/', '', code)
    code = re.sub(r'//.*$', '', code, flags=re.MULTILINE)
    return code


def _parse_module_name(code: str, result: ParsedSVA):
    """Extract module name."""
    m = re.search(r'\bmodule\s+(\w+)', code)
    if m:
        result.module_name = m.group(1)


def _parse_signals(code: str, result: ParsedSVA):
    """Extract port declarations from module header."""
    # Match the module port list
    port_match = re.search(r'module\s+\w+\s*\(([\s\S]*?)\)\s*;', code)
    if not port_match:
        return

    port_text = port_match.group(1)

    # Parse individual port declarations
    # Handles: input logic clk, input logic [31:0] data, input logic rst_n
    port_pattern = re.compile(
        r'(input|output|inout)\s+'
        r'(?:(logic|wire|reg)\s+)?'
        r'(\[\s*\d+\s*:\s*\d+\s*\]\s+)?'
        r'(\w+)'
    )

    for m in port_pattern.finditer(port_text):
        direction = m.group(1)
        sig_type = m.group(2) or "logic"
        width = m.group(3).strip() if m.group(3) else ""
        name = m.group(4)

        result.signals.append(SVASignal(
            name=name,
            direction=direction,
            width=width,
            type=sig_type,
        ))


def _parse_default_clocking(code: str, result: ParsedSVA):
    """Extract default clocking specification."""
    # default clocking cb @(posedge clk); endclocking
    m = re.search(r'default\s+clocking\s+\w*\s*@\s*\(\s*(posedge|negedge)\s+(\w+)\s*\)', code)
    if m:
        result.clock_edge = m.group(1)
        result.clock = m.group(2)
        return

    # Fallback: look for @(posedge xxx) anywhere
    m = re.search(r'@\s*\(\s*(posedge|negedge)\s+(\w+)\s*\)', code)
    if m:
        result.clock_edge = m.group(1)
        result.clock = m.group(2)


def _parse_default_disable(code: str, result: ParsedSVA):
    """Extract default disable iff condition."""
    # default disable iff (!rst_n);
    m = re.search(r'default\s+disable\s+iff\s*\(\s*(!?\s*\w+)\s*\)', code)
    if m:
        cond = m.group(1).strip()
        if cond.startswith("!"):
            result.reset = cond[1:].strip()
            result.reset_active_low = True
        else:
            result.reset = cond
            result.reset_active_low = False
        return

    # Fallback: look for disable iff in any property
    m = re.search(r'disable\s+iff\s*\(\s*(!?\s*\w+)\s*\)', code)
    if m:
        cond = m.group(1).strip()
        if cond.startswith("!"):
            result.reset = cond[1:].strip()
            result.reset_active_low = True
        else:
            result.reset = cond
            result.reset_active_low = False


def _parse_sequences(code: str, result: ParsedSVA):
    """Extract named sequence definitions."""
    # sequence s_name(params); body; endsequence
    pattern = re.compile(
        r'sequence\s+(\w+)\s*(\([^)]*\))?\s*;([\s\S]*?)endsequence',
        re.MULTILINE
    )

    for m in pattern.finditer(code):
        name = m.group(1)
        params_str = m.group(2) or ""
        body = m.group(3).strip()

        params = []
        if params_str:
            params = [p.strip() for p in params_str.strip("()").split(",") if p.strip()]

        result.sequences.append(SVASequence(
            name=name,
            body=body,
            params=params,
        ))


def _parse_properties(code: str, result: ParsedSVA):
    """Extract named property definitions."""
    # property p_name(params); body; endproperty
    pattern = re.compile(
        r'property\s+(\w+)\s*(\([^)]*\))?\s*;([\s\S]*?)endproperty',
        re.MULTILINE
    )

    for m in pattern.finditer(code):
        name = m.group(1)
        params_str = m.group(2) or ""
        body = m.group(3).strip()

        params = []
        if params_str:
            params = [p.strip() for p in params_str.strip("()").split(",") if p.strip()]

        # Check for inline clock
        clock = ""
        clock_match = re.search(r'@\s*\(\s*(posedge|negedge)\s+(\w+)\s*\)', body)
        if clock_match:
            clock = clock_match.group(2)
            # Remove inline clock from body (we handle it at module level)
            body = re.sub(r'@\s*\(\s*(posedge|negedge)\s+\w+\s*\)\s*', '', body).strip()

        # Check for inline disable iff
        reset = ""
        reset_match = re.search(r'disable\s+iff\s*\(\s*(!?\s*\w+)\s*\)', body)
        if reset_match:
            reset = reset_match.group(1).strip()
            # Remove inline disable iff from body
            body = re.sub(r'disable\s+iff\s*\(\s*!?\s*\w+\s*\)\s*', '', body).strip()

        # Strip trailing semicolons from property body (common in SVA, invalid in RTL)
        body = body.rstrip(";").strip()

        result.properties.append(SVAProperty(
            name=name,
            body=body,
            clock=clock,
            reset=reset,
            params=params,
        ))


def _parse_assertions(code: str, result: ParsedSVA):
    """Extract assert/assume/cover property statements.
    
    Handles multiple formats:
      label : assert property (prop_name);
      label : assert property (@(posedge clk) disable iff (!rst_n) prop_name);
      assert property (@(posedge `clk_in) disable iff (!`rst_n_in) prop_name);
    """
    # Preprocess: expand common backtick macros to simple names for parsing
    # This doesn't affect functionality — just lets regex match
    processed = re.sub(r'`(\w+)', r'\1', code)

    # Pattern 1: labeled assertions — label : assert/assume/cover property (...)
    labeled_pattern = re.compile(
        r'(\w+)\s*:\s*(assert|assume|cover)\s+property\s*\('
        r'(?:\s*@\s*\([^)]*\)\s*)?'            # optional inline @(posedge clk)
        r'(?:\s*disable\s+iff\s*\([^)]*\)\s*)?' # optional disable iff (...)
        r'\s*(\w+)'                              # property name
        r'(?:\s*\([^)]*\))?'                    # optional arguments
        r'\s*\)\s*;',
        re.MULTILINE
    )

    labeled_positions = set()
    for m in labeled_pattern.finditer(processed):
        label = m.group(1)
        assertion_type = m.group(2)
        prop_name = m.group(3)
        labeled_positions.add(m.start())

        result.assertions.append(SVAAssertion(
            label=label,
            type=assertion_type,
            property_name=prop_name,
        ))

    # Pattern 2: unlabeled assertions — assert/assume/cover property (...)
    unlabeled_pattern = re.compile(
        r'(assert|assume|cover)\s+property\s*\('
        r'(?:\s*@\s*\([^)]*\)\s*)?'            # optional inline @(posedge clk)
        r'(?:\s*disable\s+iff\s*\([^)]*\)\s*)?' # optional disable iff (...)
        r'\s*(\w+)'                              # property name
        r'(?:\s*\([^)]*\))?'                    # optional arguments
        r'\s*\)\s*;',
        re.MULTILINE
    )

    unnamed_counter = {}
    for m in unlabeled_pattern.finditer(processed):
        # Skip if this position was already captured as a labeled assertion
        # Check if there's a label just before this match
        pos = m.start()
        preceding = processed[max(0, pos - 60):pos].rstrip()
        if re.search(r'\w+\s*:\s*$', preceding):
            continue

        assertion_type = m.group(1)
        prop_name = m.group(2)

        # Generate unique label
        key = f"{assertion_type}_{prop_name}"
        unnamed_counter[key] = unnamed_counter.get(key, 0) + 1
        count = unnamed_counter[key]
        label = f"_auto_{assertion_type}_{prop_name}" + (f"_{count}" if count > 1 else "")

        result.assertions.append(SVAAssertion(
            label=label,
            type=assertion_type,
            property_name=prop_name,
        ))


def _parse_bind(code: str, result: ParsedSVA):
    """Extract bind statement (may be outside the module)."""
    m = re.search(r'bind\s+(\w+)\s+(\w+)\s+(\w+)\s*\((.*?)\)\s*;', code, re.DOTALL)
    if m:
        result.bind_statement = m.group(0).strip()


# ═══════════════════════════════════════════════════════════════
# PROPERTY BODY ANALYSIS
# ═══════════════════════════════════════════════════════════════

@dataclass
class PropertyAnalysis:
    """Analysis of a property body's temporal structure."""
    has_implication: bool = False
    implication_type: str = ""     # "overlapping" (|->) or "non_overlapping" (|=>)
    antecedent: str = ""           # left side of implication
    consequent: str = ""           # right side of implication
    delays: list[dict] = field(default_factory=list)        # [{type: "fixed"|"range", n: 3} or {type: "range", m: 1, n: 5}]
    repetitions: list[dict] = field(default_factory=list)   # [{type: "bounded"|"goto"|"nonconsec", n: 4}]
    system_funcs: list[str] = field(default_factory=list)   # ["$rose", "$fell", etc]
    is_simple_check: bool = False  # no temporal operators, just combinational


def analyze_property(body: str) -> PropertyAnalysis:
    """
    Analyze the temporal structure of a property body.
    Used by the lowering engine to choose the right RTL pattern.
    """
    result = PropertyAnalysis()

    # Check for implication
    if "|=>" in body:
        result.has_implication = True
        result.implication_type = "non_overlapping"
        parts = body.split("|=>", 1)
        result.antecedent = parts[0].strip()
        result.consequent = parts[1].strip() if len(parts) > 1 else ""
    elif "|->" in body:
        result.has_implication = True
        result.implication_type = "overlapping"
        parts = body.split("|->", 1)
        result.antecedent = parts[0].strip()
        result.consequent = parts[1].strip() if len(parts) > 1 else ""
    else:
        result.is_simple_check = True
        result.antecedent = body.strip()

    # Detect delays
    for m in re.finditer(r'##(\d+)', body):
        result.delays.append({"type": "fixed", "n": int(m.group(1))})
    for m in re.finditer(r'##\[(\d+):(\d+)\]', body):
        result.delays.append({"type": "range", "m": int(m.group(1)), "n": int(m.group(2))})

    # Detect repetitions
    for m in re.finditer(r'\[\*(\d+)\]', body):
        result.repetitions.append({"type": "bounded", "n": int(m.group(1))})
    for m in re.finditer(r'\[\*(\d+):(\d+)\]', body):
        result.repetitions.append({"type": "bounded_range", "m": int(m.group(1)), "n": int(m.group(2))})
    for m in re.finditer(r'\[->(\d+)\]', body):
        result.repetitions.append({"type": "goto", "n": int(m.group(1))})
    for m in re.finditer(r'\[=(\d+)\]', body):
        result.repetitions.append({"type": "nonconsec", "n": int(m.group(1))})

    # Detect system functions
    for func in ["$rose", "$fell", "$stable", "$changed", "$past", "$onehot0", "$onehot", "$countones"]:
        if func in body:
            result.system_funcs.append(func)

    # If no temporal operators at all, it's a simple combinational check
    # Note: $past, $onehot0 etc. are still "simple" from a temporal perspective
    # (they don't add implication or delay structure)
    temporal_funcs = {"$rose", "$fell", "$stable", "$changed", "$past"}
    non_temporal_only = all(f in temporal_funcs or f in ("$onehot0", "$onehot", "$countones") for f in result.system_funcs)
    if not result.delays and not result.repetitions:
        if not result.has_implication:
            result.is_simple_check = True

    return result


# ═══════════════════════════════════════════════════════════════
# UTILITY
# ═══════════════════════════════════════════════════════════════

def extract_signal_from_func(expr: str) -> str:
    """Extract signal name from $rose(sig), $fell(sig), $past(sig), etc."""
    m = re.search(r'\$(?:rose|fell|stable|changed|past)\s*\(\s*([^,)]+)\s*(?:,\s*\d+\s*)?\)', expr)
    return m.group(1).strip() if m else ""


def format_parsed_summary(parsed: ParsedSVA) -> str:
    """Human-readable summary of parsed SVA."""
    lines = [
        f"Module: {parsed.module_name}",
        f"Clock: {parsed.clock_edge} {parsed.clock}",
        f"Reset: {parsed.reset} (active {'low' if parsed.reset_active_low else 'high'})",
        f"Signals: {', '.join(s.name for s in parsed.signals)}",
        f"Properties ({len(parsed.properties)}):",
    ]
    for p in parsed.properties:
        analysis = analyze_property(p.body)
        lines.append(f"  {p.name}: {p.body[:60]}...")
        if analysis.has_implication:
            lines.append(f"    implication: {analysis.implication_type}")
        if analysis.delays:
            lines.append(f"    delays: {analysis.delays}")
        if analysis.repetitions:
            lines.append(f"    repetitions: {analysis.repetitions}")
        if analysis.system_funcs:
            lines.append(f"    system_funcs: {analysis.system_funcs}")

    lines.append(f"Assertions ({len(parsed.assertions)}):")
    for a in parsed.assertions:
        lines.append(f"  {a.label}: {a.type} property ({a.property_name})")

    if parsed.bind_statement:
        lines.append(f"Bind: {parsed.bind_statement}")

    return "\n".join(lines)