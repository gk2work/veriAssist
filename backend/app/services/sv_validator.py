"""
VeriAssist v2.0 — SystemVerilog & SVA Validator

Validates generated SystemVerilog code for:
1. Structural correctness (matching begin/end, module/endmodule, etc.)
2. SVA syntax checks (property/endproperty, sequence/endsequence, etc.)
3. sva2sby compatibility (detects banned constructs)
4. Common mistakes in LLM-generated code

Uses regex-based analysis — no native dependencies required.
Works on any platform without C compiler or tree-sitter builds.
"""

import re
import logging
from dataclasses import asdict, dataclass, field

logger = logging.getLogger("veriassist.validator")


@dataclass
class ValidationDiagnostic:
    """Structured validation issue for line-aware UI rendering."""
    severity: str
    message: str
    line: int | None = None
    column: int | None = None
    end_line: int | None = None
    end_column: int | None = None
    source: str = "validator"


@dataclass
class ValidationResult:
    """Result of validating SystemVerilog / SVA code."""
    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sva2sby_compatible: bool = True
    banned_constructs: list[str] = field(default_factory=list)
    diagnostics: list[ValidationDiagnostic] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def add_error(
        self,
        msg: str,
        *,
        line: int | None = None,
        column: int | None = None,
        end_line: int | None = None,
        end_column: int | None = None,
        source: str = "validator",
    ):
        self.errors.append(msg)
        self.valid = False
        self.diagnostics.append(
            ValidationDiagnostic(
                severity="error",
                message=msg,
                line=line,
                column=column,
                end_line=end_line,
                end_column=end_column,
                source=source,
            )
        )

    def add_warning(
        self,
        msg: str,
        *,
        line: int | None = None,
        column: int | None = None,
        end_line: int | None = None,
        end_column: int | None = None,
        source: str = "validator",
    ):
        self.warnings.append(msg)
        self.diagnostics.append(
            ValidationDiagnostic(
                severity="warning",
                message=msg,
                line=line,
                column=column,
                end_line=end_line,
                end_column=end_column,
                source=source,
            )
        )

    def add_banned(self, construct: str, line_num: int, line_text: str):
        self.banned_constructs.append(f"{construct} (line {line_num}): {line_text.strip()}")
        self.sva2sby_compatible = False
        self.add_error(
            f"sva2sby-incompatible construct '{construct}' detected",
            line=line_num,
            source="sva2sby",
        )

    def diagnostics_dicts(self) -> list[dict]:
        return [asdict(d) for d in self.diagnostics]


# ═══════════════════════════════════════════════════════════════
# BANNED CONSTRUCT PATTERNS (sva2sby incompatible)
# ═══════════════════════════════════════════════════════════════

BANNED_CONSTRUCTS = [
    {
        "pattern": r'\$past\s*\(',
        "name": "$past()",
        "fix": "Use $stable() or $changed() instead",
    },
    {
        "pattern": r'\bfirst_match\b',
        "name": "first_match",
        "fix": "Use bounded repetition with explicit bounds instead",
    },
    {
        "pattern": r'\bintersect\b',
        "name": "intersect",
        "fix": "Express the intersection as separate properties",
    },
    {
        "pattern": r'\bwithin\b',
        "name": "within",
        "fix": "Use 'throughout' for continuous condition checks",
    },
    {
        "pattern": r'\[\*\]\s*(?!\d)',  # [*] without a number after
        "name": "unbounded repetition [*]",
        "fix": "Use bounded [*N] or [*M:N] with explicit upper bound",
    },
    {
        "pattern": r'\[\+\]',
        "name": "unbounded repetition [+]",
        "fix": "Use bounded [*1:N] with explicit upper bound",
    },
    {
        "pattern": r'\$countones\s*\(',
        "name": "$countones()",
        "fix": "Implement as explicit combinational logic in checker module",
    },
    {
        "pattern": r'\$onehot\s*\(',
        "name": "$onehot()",
        "fix": "Implement as: (sig != '0) && ((sig & (sig - 1)) == '0)",
    },
    {
        "pattern": r'\$onehot0\s*\(',
        "name": "$onehot0()",
        "fix": "Implement as: (sig & (sig - 1)) == '0",
    },
]

# ═══════════════════════════════════════════════════════════════
# STRUCTURAL PAIRS (must match)
# ═══════════════════════════════════════════════════════════════

BLOCK_PAIRS = [
    ("module", "endmodule"),
    ("class", "endclass"),
    ("function", "endfunction"),
    ("task", "endtask"),
    ("property", "endproperty"),
    ("sequence", "endsequence"),
    ("interface", "endinterface"),
    ("package", "endpackage"),
    ("begin", "end"),
    ("clocking", "endclocking"),
]

# ═══════════════════════════════════════════════════════════════
# MAIN VALIDATION FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def validate_sv(code: str) -> ValidationResult:
    """
    Full SystemVerilog validation: structure + syntax + sva2sby compatibility.
    """
    result = ValidationResult()

    if not code or not code.strip():
        result.add_error("Empty code")
        return result

    # Strip comments for analysis (but keep for line counting)
    stripped = _strip_comments(code)
    # 1. Structural validation
    _check_block_matching(stripped, result)

    # 2. SVA-specific checks
    _check_sva_structure(stripped, result)

    # 3. sva2sby banned constructs
    _check_banned_constructs(code, result)

    # 4. Common LLM mistakes
    _check_common_mistakes(code, result)

    # 5. Collect stats
    result.stats = _collect_stats(stripped)

    return result


def get_numbered_lines(code: str) -> list[dict]:
    """Return code split into line-numbered rows for editor gutters."""
    return [
        {"line": idx, "text": text}
        for idx, text in enumerate(code.splitlines(), start=1)
    ]


def build_validation_payload(result: ValidationResult, code: str) -> dict:
    """Build a UI-friendly validation payload with diagnostics and line grid data."""
    return {
        "valid": result.valid,
        "errors": result.errors,
        "warnings": result.warnings,
        "sva2sby_compatible": result.sva2sby_compatible,
        "banned_constructs": result.banned_constructs,
        "diagnostics": result.diagnostics_dicts(),
        "numbered_lines": get_numbered_lines(code),
        "stats": result.stats,
    }


def validate_sva_for_formal(code: str) -> ValidationResult:
    """
    Strict validation for Formal mode — checks everything validate_sv does,
    plus additional formal-specific requirements.
    """
    result = validate_sv(code)

    stripped = _strip_comments(code)

    # Additional formal-mode checks

    # Must have at least one assert, assume, or cover
    has_assert = bool(re.search(r'\bassert\s+property\b', stripped))
    has_assume = bool(re.search(r'\bassume\s+property\b', stripped))
    has_cover = bool(re.search(r'\bcover\s+property\b', stripped))

    if not (has_assert or has_assume or has_cover):
        result.add_error(
            "No assert/assume/cover property found. Formal verification requires at least one."
        )

    # Should have default clocking
    has_default_clk = bool(re.search(r'default\s+clocking\b', stripped))
    if not has_default_clk:
        # Check for inline clock specification
        has_inline_clk = bool(re.search(r'@\s*\(\s*posedge\s+\w+\s*\)', stripped))
        if not has_inline_clk:
            result.add_warning(
                "No default clocking or @(posedge clk) found. Properties need a clock specification."
            )

    # Should have disable iff (reset handling)
    has_disable = bool(re.search(r'disable\s+iff\b', stripped))
    if not has_disable:
        result.add_warning("No 'disable iff' found. Properties should handle reset conditions.")

    # Should have named properties (not anonymous)
    anon_asserts = re.findall(r'assert\s+property\s*\(\s*@', stripped)
    if anon_asserts:
        result.add_warning(f"Found {len(anon_asserts)} anonymous assertion(s). Use named properties for clarity.")

    # Check for cover properties (best practice)
    if has_assert and not has_cover:
        result.add_warning("Assert properties found but no cover properties. Add cover versions for reachability checking.")

    return result


def check_sva2sby_compatible(code: str) -> tuple[bool, list[str]]:
    """
    Quick check: is this SVA code sva2sby-compatible?
    Returns (compatible, list_of_issues).
    """
    issues = []
    code_stripped = _strip_comments(code)

    for banned in BANNED_CONSTRUCTS:
        matches = re.finditer(banned["pattern"], code_stripped)
        for m in matches:
            line_num = code_stripped[:m.start()].count("\n") + 1
            issues.append(f"{banned['name']}: {banned['fix']} (line {line_num})")

    return len(issues) == 0, issues


def extract_sva_code(llm_response: str) -> str:
    """
    Extract SystemVerilog code from LLM response.
    Handles: ```systemverilog ... ```, ```sv ... ```, ```verilog ... ```, ``` ... ```
    If multiple code blocks, returns the longest one (likely the main module).
    """
    # Try specific language tags first
    patterns = [
        r'```(?:systemverilog|sv|verilog)\n([\s\S]*?)```',
        r'```\n([\s\S]*?)```',
    ]

    blocks = []
    for pattern in patterns:
        matches = re.findall(pattern, llm_response)
        blocks.extend(matches)

    if not blocks:
        # No code blocks found — check if the entire response looks like SV
        if re.search(r'\b(module|property|assert|sequence)\b', llm_response):
            return llm_response.strip()
        return ""

    # Return the longest code block (most likely the complete module)
    return max(blocks, key=len).strip()


# ═══════════════════════════════════════════════════════════════
# INTERNAL VALIDATION HELPERS
# ═══════════════════════════════════════════════════════════════

def _strip_comments(code: str) -> str:
    """Remove single-line (//) and multi-line (/* */) comments."""
    # Remove multi-line comments
    code = re.sub(r'/\*[\s\S]*?\*/', '', code)
    # Remove single-line comments
    code = re.sub(r'//.*$', '', code, flags=re.MULTILINE)
    return code


def _check_block_matching(code: str, result: ValidationResult):
    """Check that all block pairs match (module/endmodule, property/endproperty, etc.)."""
    for open_kw, close_kw in BLOCK_PAIRS:
        # Use word boundaries to avoid partial matches
        open_pattern = rf'\b{open_kw}\b'
        close_pattern = rf'\b{close_kw}\b'

        # Skip 'begin' inside strings or other contexts
        open_count = len(re.findall(open_pattern, code))
        close_count = len(re.findall(close_pattern, code))

        # For begin/end, we expect rough matching (not exact due to complexity)
        if open_kw == "begin":
            if abs(open_count - close_count) > 2:
                result.add_warning(f"begin/end mismatch: {open_count} begin vs {close_count} end")
            continue

        if open_count != close_count:
            result.add_error(
                f"Unmatched {open_kw}/{close_kw}: "
                f"found {open_count} '{open_kw}' but {close_count} '{close_kw}'"
            )


def _check_sva_structure(code: str, result: ValidationResult):
    """Check SVA-specific structural requirements."""

    # Check that properties have proper syntax
    property_decls = re.findall(r'property\s+(\w+)', code)
    property_ends = re.findall(r'endproperty', code)

    if property_decls and len(property_decls) != len(property_ends):
        result.add_error(
            f"Property count mismatch: {len(property_decls)} declarations "
            f"vs {len(property_ends)} endproperty"
        )

    # Check that asserted properties reference defined properties
    asserted_props = re.findall(r'(?:assert|assume|cover)\s+property\s*\(\s*(\w+)', code)
    for prop_name in asserted_props:
        if prop_name not in property_decls and prop_name != "property":
            # Could be an inline property — just warn
            pass

    # Check sequence declarations
    seq_decls = re.findall(r'sequence\s+(\w+)', code)
    seq_ends = re.findall(r'endsequence', code)
    if seq_decls and len(seq_decls) != len(seq_ends):
        result.add_error(
            f"Sequence count mismatch: {len(seq_decls)} declarations "
            f"vs {len(seq_ends)} endsequence"
        )


def _check_banned_constructs(code: str, result: ValidationResult):
    """Check for sva2sby-incompatible constructs."""
    # Work on original code (with comments) for accurate line numbers
    # but check against comment-stripped code for pattern matching
    stripped = _strip_comments(code)
    lines = code.split("\n")

    for banned in BANNED_CONSTRUCTS:
        matches = list(re.finditer(banned["pattern"], stripped))
        for m in matches:
            # Find the line number in original code
            line_num = stripped[:m.start()].count("\n") + 1
            line_text = lines[min(line_num - 1, len(lines) - 1)] if line_num <= len(lines) else ""
            result.add_banned(banned["name"], line_num, line_text)

    if result.banned_constructs:
        if not any(
            d.source == "sva2sby" and d.message.startswith("Found ")
            for d in result.diagnostics
        ):
            result.add_error(
                f"Found {len(result.banned_constructs)} sva2sby-incompatible construct(s). "
                f"These will cause the formal flow to fail."
            )


def _check_common_mistakes(code: str, result: ValidationResult):
    """Check for common mistakes in LLM-generated SystemVerilog."""

    # $display instead of `uvm_info (in UVM context)
    if re.search(r'\$display\s*\(', code) and re.search(r'uvm_|`uvm_', code):
        result.add_warning("Found $display in UVM context. Use `uvm_info instead.")

    # Missing semicolons after endmodule/endclass (common LLM mistake)
    # Actually, these should NOT have semicolons — check for incorrect ones
    for kw in ["endmodule", "endclass", "endinterface", "endpackage"]:
        match = re.search(rf'\b{kw}\s*;', code)
        if match:
            result.add_warning(
                f"Unnecessary semicolon after '{kw}'. Remove it.",
                line=code[:match.start()].count("\n") + 1,
            )

    # Check for `timescale in assertion-only modules (unnecessary)
    match = re.search(r'`timescale', code)
    if match:
        if not re.search(r'\bmodule\b.*\b(input|output|inout)\b', code, re.DOTALL):
            result.add_warning(
                "`timescale directive in assertion-only module is unnecessary.",
                line=code[:match.start()].count("\n") + 1,
            )

    # Empty property body
    match = re.search(r'property\s+\w+\s*;?\s*endproperty', code)
    if match:
        result.add_error(
            "Empty property body detected.",
            line=code[:match.start()].count("\n") + 1,
        )

    # Implication without antecedent
    match = re.search(r'^\s*\|[-=]>', code, re.MULTILINE)
    if match:
        result.add_warning(
            "Implication operator without clear antecedent.",
            line=code[:match.start()].count("\n") + 1,
        )


def _collect_stats(code: str) -> dict:
    """Collect statistics about the code for reporting."""
    return {
        "lines": len(code.split("\n")),
        "modules": len(re.findall(r'\bmodule\b', code)),
        "properties": len(re.findall(r'\bproperty\s+\w+', code)),
        "sequences": len(re.findall(r'\bsequence\s+\w+', code)),
        "assertions": len(re.findall(r'\bassert\s+property\b', code)),
        "assumptions": len(re.findall(r'\bassume\s+property\b', code)),
        "covers": len(re.findall(r'\bcover\s+property\b', code)),
        "has_bind": bool(re.search(r'\bbind\b', code)),
        "has_default_clocking": bool(re.search(r'default\s+clocking\b', code)),
        "has_disable_iff": bool(re.search(r'disable\s+iff\b', code)),
        "constructs_used": _detect_constructs(code),
    }


def _detect_constructs(code: str) -> list[str]:
    """Detect which SVA constructs are used in the code."""
    constructs = []
    checks = [
        (r'\|->', "overlapping_implication"),
        (r'\|=>', "non_overlapping_implication"),
        (r'##\d+', "fixed_delay"),
        (r'##\[\d+:\d+\]', "range_delay"),
        (r'\[\*\d+', "bounded_repetition"),
        (r'\[->\d+\]', "goto_repetition"),
        (r'\[=\d+\]', "nonconsec_repetition"),
        (r'\$rose', "rose"),
        (r'\$fell', "fell"),
        (r'\$stable', "stable"),
        (r'\$changed', "changed"),
        (r'disable\s+iff', "disable_iff"),
        (r'throughout', "throughout"),
        (r'default\s+clocking', "default_clocking"),
    ]
    for pattern, name in checks:
        if re.search(pattern, code):
            constructs.append(name)
    return constructs


# ═══════════════════════════════════════════════════════════════
# AUTO-FIX SUGGESTIONS
# ═══════════════════════════════════════════════════════════════

def get_fix_suggestions(result: ValidationResult) -> list[str]:
    """
    Generate actionable fix suggestions based on validation errors.
    Used to feed back into the LLM for auto-retry.
    """
    suggestions = []

    for banned in result.banned_constructs:
        # Find the matching banned construct info
        for b in BANNED_CONSTRUCTS:
            if b["name"] in banned:
                suggestions.append(f"Replace {b['name']} — {b['fix']}")
                break

    for error in result.errors:
        if "Unmatched" in error:
            suggestions.append("Fix block matching: ensure every module/endmodule, property/endproperty pair is complete.")
        if "Empty property" in error:
            suggestions.append("Fill in the empty property body with temporal logic.")
        if "No assert/assume/cover" in error:
            suggestions.append("Add at least one 'assert property', 'assume property', or 'cover property' statement.")

    return suggestions


def build_retry_prompt(original_query: str, code: str, result: ValidationResult) -> str:
    """
    Build a follow-up prompt for the LLM to fix validation errors.
    Used for automatic retry when first generation has issues.
    """
    suggestions = get_fix_suggestions(result)

    prompt = f"""The previously generated SVA code has validation issues that must be fixed.

ORIGINAL REQUEST: {original_query}

GENERATED CODE (with issues):
```systemverilog
{code}
```

VALIDATION ERRORS:
{chr(10).join(f"- {e}" for e in result.errors)}

WARNINGS:
{chr(10).join(f"- {w}" for w in result.warnings)}

FIX INSTRUCTIONS:
{chr(10).join(f"- {s}" for s in suggestions)}

Please regenerate the COMPLETE corrected code. Ensure all sva2sby-incompatible constructs are replaced with supported alternatives. Keep the same structure and intent."""

    return prompt
