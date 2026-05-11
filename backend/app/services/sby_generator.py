"""
VeriAssist v2.0 — SymbiYosys Project Generator

Creates complete SymbiYosys (.sby) project directories containing:
- DUT source files
- Lowered formal monitor (from sva_lowering.py)
- .sby configuration file
- Ready to run: sby -f project.sby

The generator never modifies the user's source tree — everything
is staged into a clean working directory.
"""

import os
import re
import shutil
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
import xml.etree.ElementTree as ET

logger = logging.getLogger("veriassist.sby_gen")

# Base directory for all formal work
FORMAL_WORK_DIR = Path(__file__).parent.parent.parent / "data" / "formal_work"


@dataclass
class SbyConfig:
    """Configuration for a SymbiYosys project."""
    project_name: str = "formal_check"
    mode: str = "bmc"              # bmc | prove | cover
    depth: int = 20                # BMC depth (number of cycles)
    engine: str = "smtbmc"         # smtbmc | abc | aiger
    solver: str = ""               # yices | z3 | boolector (empty = default)
    timeout: int = 300             # seconds
    top_module: str = ""           # DUT top module name
    monitor_module: str = ""       # lowered formal monitor module name
    dut_files: list[str] = field(default_factory=list)
    monitor_file: str = ""         # lowered monitor .sv file
    multiclock: bool = False


@dataclass
class SbyProject:
    """A staged SymbiYosys project ready to run."""
    work_dir: str
    sby_file: str
    dut_files: list[str]
    monitor_file: str
    config: SbyConfig


def generate_sby_project(
    config: SbyConfig,
    dut_contents: dict[str, str],    # {filename: content}
    monitor_content: str,             # lowered RTL from sva_lowering
    work_dir: Optional[str] = None,
) -> SbyProject:
    """
    Generate a complete SymbiYosys project.

    Args:
        config: SbyConfig with project settings
        dut_contents: dict mapping filenames to their SystemVerilog content
        monitor_content: lowered formal monitor code (from sva_lowering.py)
        work_dir: optional custom work directory path

    Returns:
        SbyProject with paths to all generated files
    """
    # Create work directory
    if work_dir:
        project_dir = Path(work_dir)
    else:
        FORMAL_WORK_DIR.mkdir(parents=True, exist_ok=True)
        project_dir = FORMAL_WORK_DIR / config.project_name

    # Clean existing if present
    if project_dir.exists():
        shutil.rmtree(project_dir)

    project_dir.mkdir(parents=True, exist_ok=True)
    src_dir = project_dir / "src"
    src_dir.mkdir()

    logger.info(f"Staging SymbiYosys project in {project_dir}")

    # Write DUT files
    staged_dut_files = []
    for filename, content in dut_contents.items():
        filepath = src_dir / filename
        filepath.write_text(content)
        staged_dut_files.append(f"src/{filename}")
        logger.info(f"  Staged DUT: {filename}")

    # Write monitor file
    monitor_filename = f"{config.monitor_module or config.project_name}_monitor.sv"
    monitor_path = src_dir / monitor_filename
    monitor_path.write_text(monitor_content)
    staged_monitor = f"src/{monitor_filename}"
    logger.info(f"  Staged monitor: {monitor_filename}")

    # Generate .sby file
    # Generate wrapper that instantiates DUT + monitor together
    wrapper_content = _generate_wrapper(config, dut_contents, monitor_content)
    has_wrapper = bool(wrapper_content)
    if wrapper_content:
        wrapper_path = src_dir / "formal_wrapper.sv"
        wrapper_path.write_text(wrapper_content)
        logger.info(f"  Generated: formal_wrapper.sv")

    # Generate .sby file
    sby_content = _generate_sby_config(config, staged_dut_files, staged_monitor, has_wrapper=has_wrapper)
    sby_filename = f"{config.project_name}.sby"
    sby_path = project_dir / sby_filename
    sby_path.write_text(sby_content)
    logger.info(f"  Generated: {sby_filename}")

    project = SbyProject(
        work_dir=str(project_dir),
        sby_file=str(sby_path),
        dut_files=staged_dut_files,
        monitor_file=staged_monitor,
        config=config,
    )

    logger.info(f"SymbiYosys project ready: {sby_path}")
    return project


def _generate_sby_config(
    config: SbyConfig,
    dut_files: list[str],
    monitor_file: str,
    has_wrapper: bool = False,
) -> str:
    """Generate the .sby configuration file content."""
    lines = []

    # Tasks
    lines.append("[tasks]")
    lines.append(config.mode)
    lines.append("")

    # Options
    lines.append("[options]")
    lines.append(f"{config.mode}: mode {config.mode}")
    lines.append(f"{config.mode}: depth {config.depth}")
    if config.timeout:
        lines.append(f"{config.mode}: timeout {config.timeout}")
    lines.append("")

    # Engines
    lines.append("[engines]")
    engine_line = config.engine
    if config.solver:
        engine_line += f" {config.solver}"
    lines.append(engine_line)
    lines.append("")

    # Script — filenames only (no path prefix, sby copies files to its workdir root)
    lines.append("[script]")

    for f in dut_files:
        fname = f.split("/")[-1]  # strip src/ prefix
        lines.append(f"read -formal {fname}")

    monitor_fname = monitor_file.split("/")[-1]
    lines.append(f"read -formal {monitor_fname}")

    has_wrapper = bool(has_wrapper and config.top_module and config.monitor_module)
    if has_wrapper:
        lines.append(f"read -formal formal_wrapper.sv")
        lines.append(f"prep -top formal_wrapper")
    elif config.top_module:
        lines.append(f"prep -top {config.top_module}")
    else:
        lines.append("prep")
    lines.append("")

    # Files — maps source paths to destination filenames
    # Format: <dest_name> <source_path> OR just <source_path> (copies with same name)
    lines.append("[files]")
    for f in dut_files:
        fname = f.split("/")[-1]
        lines.append(f"{fname} {f}")
    lines.append(f"{monitor_fname} {monitor_file}")
    if has_wrapper:
        lines.append(f"formal_wrapper.sv src/formal_wrapper.sv")
    lines.append("")

    return "\n".join(lines)


def _generate_wrapper(
    config: SbyConfig,
    dut_contents: dict[str, str],
    monitor_content: str,
) -> Optional[str]:
    """
    Generate a wrapper module that instantiates both the DUT and the
    formal monitor, connecting them with matching signals.

    This is needed because the lowered monitor is a separate module
    that needs to observe the DUT's signals.
    """
    if not config.top_module or not config.monitor_module:
        return None

    # Extract DUT ports by parsing the first DUT file
    dut_ports = _extract_module_ports(list(dut_contents.values())[0], config.top_module)
    if not dut_ports:
        logger.warning(f"Could not extract ports from DUT module '{config.top_module}'")
        return None

    dut_port_names = {port["name"] for port in dut_ports}
    actual_clock, actual_reset = _pick_clock_reset_ports(dut_ports)

    lines = []
    lines.append("`ifdef FORMAL")
    lines.append(f"module formal_wrapper (")
    lines.append(f"    input wire clk,")
    lines.append(f"    input wire rst_n")
    lines.append(f");")
    lines.append("")

    if actual_clock and actual_clock != "clk":
        lines.append(f"    wire {actual_clock} = clk;")
    if actual_reset and actual_reset != "rst_n":
        lines.append(f"    wire {actual_reset} = rst_n;")
    if actual_clock or actual_reset:
        lines.append("")

    # Declare wires for all DUT ports (except clk/rst)
    for port in dut_ports:
        if port["name"] in {"clk", "rst_n", "rst", "reset", actual_clock, actual_reset}:
            continue
        width = port.get("width", "")
        # Resolve parameterized widths to safe defaults for formal
        # If width contains non-numeric characters (like $clog2, WIDTH, DEPTH),
        # replace with a reasonable default
        if width and not re.match(r'^\[\s*\d+\s*:\s*\d+\s*\]$', width):
            # Try to evaluate simple expressions, otherwise use [7:0]
            width = "[7:0]"
        width_str = f"{width} " if width else ""
        if port["direction"] == "output":
            lines.append(f"    wire {width_str}{port['name']};")
        else:
            lines.append(f"    (* anyseq *) wire {width_str}{port['name']};")

    lines.append("")

    # Instantiate DUT — use .* for parameterized modules to avoid width mismatches
    lines.append(f"    {config.top_module} u_dut (")
    port_connections = []
    for port in dut_ports:
        port_connections.append(f"        .{port['name']}({port['name']})")
    lines.append(",\n".join(port_connections))
    lines.append(f"    );")
    lines.append("")

    # Instantiate monitor — connect only monitor ports (subset of DUT ports)
    monitor_ports = _extract_module_ports(monitor_content, config.monitor_module)
    if monitor_ports:
        mon_connections = []
        extra_monitor_decls = []
        for port in monitor_ports:
            resolved_name = _resolve_monitor_signal(port["name"], dut_port_names, actual_clock, actual_reset)
            if resolved_name is None:
                width = port.get("width", "")
                if width and not re.match(r'^\[\s*\d+\s*:\s*\d+\s*\]$', width):
                    width = "[7:0]"
                width_str = f"{width} " if width else ""
                extra_monitor_decls.append(f"    (* anyseq *) wire {width_str}{port['name']};")
                resolved_name = port["name"]
        if extra_monitor_decls:
            lines.extend(extra_monitor_decls)
            lines.append("")
        lines.append(f"    {config.monitor_module} u_monitor (")
        for port in monitor_ports:
            resolved_name = _resolve_monitor_signal(port["name"], dut_port_names, actual_clock, actual_reset)
            if resolved_name is None:
                resolved_name = port["name"]
            mon_connections.append(f"        .{port['name']}({resolved_name})")
        lines.append(",\n".join(mon_connections))
    else:
        lines.append(f"    {config.monitor_module} u_monitor (")
        lines.append(f"        .*")
    lines.append(f"    );")
    lines.append("")

    # Initial reset assumption: rst_n must be low at step 0
    # This ensures DUT registers initialize before assertions fire
    lines.append(f"    // Assume reset is active for at least the first cycle")
    lines.append(f"    reg _va_past_valid;")
    lines.append(f"    always @(posedge clk) begin")
    lines.append(f"        if (!_va_past_valid)")
    lines.append(f"            _va_past_valid <= 1;")
    lines.append(f"    end")
    lines.append(f"    initial _va_past_valid = 0;")
    lines.append(f"    always @(*) begin")
    lines.append(f"        if (!_va_past_valid)")
    lines.append(f"            assume(!{actual_reset or 'rst_n'});")
    lines.append(f"    end")
    lines.append("")

    lines.append(f"endmodule")
    lines.append("`endif")

    return "\n".join(lines)


def _extract_module_ports(code: str, module_name: str) -> list[dict]:
    """Extract port list from a module declaration.
    Handles parameterized modules: module name #(params)(ports);
    """

    # Try with specific module name — with optional #(params)
    pattern = re.compile(
        rf'module\s+{re.escape(module_name)}\s*'
        r'(?:#\s*\([\s\S]*?\)\s*)?'   # optional #(parameter list)
        r'\(([\s\S]*?)\)\s*;',
        re.MULTILINE
    )
    m = pattern.search(code)
    if not m:
        # Try without specific module name — with optional #(params)
        m = re.search(
            r'module\s+\w+\s*(?:#\s*\([\s\S]*?\)\s*)?\(([\s\S]*?)\)\s*;',
            code
        )
        if not m:
            return []

    port_text = m.group(1)
    ports = []

    # Match ports with optional width containing expressions like $clog2(DEPTH)
    port_pattern = re.compile(
        r'(input|output|inout)\s+'
        r'(?:(wire|logic|reg)\s+)?'
        r'(\[[\s\S]*?\]\s+)?'       # width — now handles $clog2(X):0 etc.
        r'(\w+)'
    )

    for pm in port_pattern.finditer(port_text):
        ports.append({
            "direction": pm.group(1),
            "type": pm.group(2) or "wire",
            "width": pm.group(3).strip() if pm.group(3) else "",
            "name": pm.group(4),
        })

    if ports:
        return ports

    header_names = _extract_header_port_names(port_text)
    if not header_names:
        return []

    return _extract_non_ansi_port_decls(code, header_names)


def _extract_header_port_names(port_text: str) -> list[str]:
    """Extract ordered port names from a classic non-ANSI module header."""
    cleaned = re.sub(r'/\*[\s\S]*?\*/', '', port_text)
    cleaned = re.sub(r'//.*$', '', cleaned, flags=re.MULTILINE)
    names = []
    for item in cleaned.split(","):
        name = item.strip()
        if not name:
            continue
        m = re.search(r'(\w+)$', name)
        if m:
            names.append(m.group(1))
    return names


def _extract_non_ansi_port_decls(code: str, header_names: list[str]) -> list[dict]:
    """Extract classic Verilog port declarations from the module body."""
    header_set = set(header_names)
    decl_pattern = re.compile(
        r'\b(input|output|inout)\b\s+'
        r'(?:(wire|logic|reg)\s+)?'
        r'(\[[^\]]+\]\s+)?'
        r'([^;]+);'
    )

    ports_by_name: dict[str, dict] = {}
    for match in decl_pattern.finditer(code):
        direction = match.group(1)
        sig_type = match.group(2) or "wire"
        width = match.group(3).strip() if match.group(3) else ""
        names_blob = match.group(4)
        for raw_name in names_blob.split(","):
            name = raw_name.strip()
            if not name:
                continue
            name_match = re.search(r'(\w+)$', name)
            if not name_match:
                continue
            final_name = name_match.group(1)
            if final_name in header_set:
                ports_by_name[final_name] = {
                    "direction": direction,
                    "type": sig_type,
                    "width": width,
                    "name": final_name,
                }

    return [ports_by_name[name] for name in header_names if name in ports_by_name]


def _pick_clock_reset_ports(dut_ports: list[dict]) -> tuple[str, str]:
    """Best-effort detection of DUT clock/reset port names."""
    names = [port["name"] for port in dut_ports]

    def pick(candidates: list[str], default: str) -> str:
        for candidate in candidates:
            if candidate in names:
                return candidate
        return default

    clock_name = pick(["clk", "clock", "clk_in", "clk_i"], "clk")
    reset_name = pick(["rst_n", "reset_n", "rst", "reset", "rst_n_in"], "rst_n")
    return clock_name, reset_name


def _resolve_monitor_signal(
    monitor_name: str,
    dut_port_names: set[str],
    actual_clock: str,
    actual_reset: str,
) -> Optional[str]:
    """Map lowered monitor signal names back to DUT or wrapper signals."""
    if monitor_name in dut_port_names:
        return monitor_name
    if monitor_name == "clk_in":
        return actual_clock or "clk"
    if monitor_name == "rst_n_in":
        return actual_reset or "rst_n"

    for suffix in ("_in", "_out"):
        if monitor_name.endswith(suffix):
            candidate = monitor_name[: -len(suffix)]
            if candidate in dut_port_names:
                return candidate

    return None

    


# ═══════════════════════════════════════════════════════════════
# QUICK PROJECT GENERATION (for API use)
# ═══════════════════════════════════════════════════════════════

def quick_generate(
    sva_code: str,
    dut_code: str,
    dut_filename: str = "dut.sv",
    dut_top: str = "",
    mode: str = "bmc",
    depth: int = 20,
    solver: str = "",
    project_name: str = "formal_check",
) -> SbyProject:
    """
    All-in-one: parse SVA → lower → stage sby project.
    Used by the formal API endpoint.
    """
    from app.services.sva_parser import parse_sva
    from app.services.sva_lowering import SVALoweringEngine

    # Parse and lower SVA
    parsed = parse_sva(sva_code)
    engine = SVALoweringEngine()
    monitor_rtl = engine.lower(parsed)

    # Auto-detect DUT top module if not specified
    if not dut_top:
        import re
        m = re.search(r'module\s+(\w+)', dut_code)
        dut_top = m.group(1) if m else ""

    # Configure
    config = SbyConfig(
        project_name=project_name,
        mode=mode,
        depth=depth,
        engine="smtbmc",
        solver=solver,
        top_module=dut_top,
        monitor_module=parsed.module_name,
    )

    # Generate project
    return generate_sby_project(
        config=config,
        dut_contents={dut_filename: dut_code},
        monitor_content=monitor_rtl,
    )


def quick_generate_standalone(
    sva_code: str,
    mode: str = "bmc",
    depth: int = 20,
    solver: str = "",
    project_name: str = "formal_check",
) -> SbyProject:
    """
    Generate a standalone formal project (no separate DUT).
    The monitor itself IS the top module with assertions.
    Used when checking properties directly without a DUT.
    """
    from app.services.sva_parser import parse_sva
    from app.services.sva_lowering import SVALoweringEngine

    parsed = parse_sva(sva_code)
    engine = SVALoweringEngine()
    monitor_rtl = engine.lower(parsed)

    config = SbyConfig(
        project_name=project_name,
        mode=mode,
        depth=depth,
        engine="smtbmc",
        solver=solver,
        top_module=parsed.module_name,
        monitor_module="",  # no separate monitor — it IS the top
    )

    # No DUT files — monitor is the only file
    FORMAL_WORK_DIR.mkdir(parents=True, exist_ok=True)
    project_dir = FORMAL_WORK_DIR / project_name

    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)

    # Write monitor as the only source file
    monitor_filename = f"{project_name}_monitor.sv"
    monitor_path = project_dir / monitor_filename
    monitor_path.write_text(monitor_rtl)

    # Generate minimal .sby
    sby_lines = [
        "[tasks]",
        config.mode,
        "",
        "[options]",
        f"{config.mode}: mode {config.mode}",
        f"{config.mode}: depth {config.depth}",
        "",
        "[engines]",
        f"{config.engine}" + (f" {config.solver}" if config.solver else ""),
        "",
        "[script]",
        f"read -formal {monitor_filename}",
        f"prep -top {parsed.module_name}",
        "",
        "[files]",
        monitor_filename,
        "",
    ]

    sby_filename = f"{project_name}.sby"
    sby_path = project_dir / sby_filename
    sby_path.write_text("\n".join(sby_lines))

    logger.info(f"Standalone formal project ready: {sby_path}")

    return SbyProject(
        work_dir=str(project_dir),
        sby_file=str(sby_path),
        dut_files=[],
        monitor_file=monitor_filename,
        config=config,
    )


def generate_raw_sby_project(
    design_file_contents: dict[str, str],   # {filename: content}
    sva_file_contents: dict[str, str],       # {filename: content}
    mode: str = "bmc",
    depth: int = 20,
    solver: str = "",
    top_module: str = "",
    timeout: int = 300,
    project_name: str = "fv_raw",
) -> SbyProject:
    """
    Generate a SymbiYosys project directly from raw design + SVA files,
    bypassing the SVA lowering engine entirely.  Used by the file-upload
    endpoint so that native bind statements and assertions are preserved.
    """
    FORMAL_WORK_DIR.mkdir(parents=True, exist_ok=True)
    project_dir = FORMAL_WORK_DIR / project_name
    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)

    # Write all files flat into the project dir
    all_filenames: list[str] = []
    for fname, content in {**design_file_contents, **sva_file_contents}.items():
        safe_name = Path(fname).name          # strip any path components
        (project_dir / safe_name).write_text(content)
        all_filenames.append(safe_name)
        logger.info(f"  [raw] Staged: {safe_name}")

    engine_line = "smtbmc"
    if solver:
        engine_line += f" {solver}"

    script_lines = [f"read -formal {fn}" for fn in all_filenames]
    if top_module:
        script_lines.append(f"prep -top {top_module}")
    else:
        script_lines.append("prep")

    sby_lines = [
        "[tasks]",
        mode,
        "",
        "[options]",
        f"{mode}: mode {mode}",
        f"{mode}: depth {depth}",
        f"{mode}: timeout {timeout}",
        "",
        "[engines]",
        engine_line,
        "",
        "[script]",
        *script_lines,
        "",
        "[files]",
        *all_filenames,
        "",
    ]

    sby_filename = f"{project_name}.sby"
    sby_path = project_dir / sby_filename
    sby_path.write_text("\n".join(sby_lines))
    logger.info(f"Raw formal project ready: {sby_path}")

    config = SbyConfig(
        project_name=project_name,
        mode=mode,
        depth=depth,
        engine="smtbmc",
        solver=solver,
        timeout=timeout,
        top_module=top_module,
    )
    return SbyProject(
        work_dir=str(project_dir),
        sby_file=str(sby_path),
        dut_files=list(design_file_contents.keys()),
        monitor_file="",
        config=config,
    )


def generate_standalone_project_from_monitor(
    monitor_rtl: str,
    top_module: str,
    mode: str = "bmc",
    depth: int = 20,
    solver: str = "",
    project_name: str = "formal_check",
    work_dir: Optional[str] = None,
) -> SbyProject:
    """
    Stage a standalone SymbiYosys project from already-lowered monitor RTL.
    """
    config = SbyConfig(
        project_name=project_name,
        mode=mode,
        depth=depth,
        engine="smtbmc",
        solver=solver,
        top_module=top_module,
        monitor_module="",
    )

    if work_dir:
        project_dir = Path(work_dir)
    else:
        FORMAL_WORK_DIR.mkdir(parents=True, exist_ok=True)
        project_dir = FORMAL_WORK_DIR / project_name

    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)

    monitor_filename = f"{project_name}_monitor.sv"
    monitor_path = project_dir / monitor_filename
    monitor_path.write_text(monitor_rtl)

    sby_lines = [
        "[tasks]",
        config.mode,
        "",
        "[options]",
        f"{config.mode}: mode {config.mode}",
        f"{config.mode}: depth {config.depth}",
        "",
        "[engines]",
        f"{config.engine}" + (f" {config.solver}" if config.solver else ""),
        "",
        "[script]",
        f"read -formal {monitor_filename}",
        f"prep -top {top_module}",
        "",
        "[files]",
        monitor_filename,
        "",
    ]

    sby_filename = f"{project_name}.sby"
    sby_path = project_dir / sby_filename
    sby_path.write_text("\n".join(sby_lines))

    logger.info(f"Standalone formal project ready: {sby_path}")

    return SbyProject(
        work_dir=str(project_dir),
        sby_file=str(sby_path),
        dut_files=[],
        monitor_file=monitor_filename,
        config=config,
    )


# ═══════════════════════════════════════════════════════════════
# RESULT PARSING
# ═══════════════════════════════════════════════════════════════

@dataclass
class SbyResult:
    """Parsed result from a SymbiYosys run."""
    status: str = "unknown"        # PASS | FAIL | TIMEOUT | ERROR
    return_code: int = -1
    elapsed_seconds: float = 0.0
    depth_reached: int = 0
    failed_assertions: list[dict] = field(default_factory=list)  # [{name, file, line, step}]
    counterexample_vcd: str = ""   # path to VCD file if FAIL
    engine_output: str = ""        # raw sby stdout
    stderr_output: str = ""        # raw sby stderr
    error_message: str = ""
    detailed_logs: dict[str, str] = field(default_factory=dict)
    log_paths: dict[str, str] = field(default_factory=dict)
    assertion_results: list[dict] = field(default_factory=list)  # [{name, status, type, location, message, tracefile}]


def parse_sby_output(stdout: str, stderr: str, returncode: int, work_dir: str) -> SbyResult:
    """Parse SymbiYosys stdout/stderr into structured result."""
    import re

    detailed_logs, log_paths = _collect_sby_logs(work_dir)
    result = SbyResult(
        return_code=returncode,
        engine_output=stdout,
        stderr_output=stderr,
        detailed_logs=detailed_logs,
        log_paths=log_paths,
    )

    # Determine status from return code and output
    if returncode == 0:
        result.status = "PASS"
    elif returncode == 2:
        result.status = "FAIL"
    elif returncode == 4:
        result.status = "TIMEOUT"
    else:
        result.status = "ERROR"
        result.error_message = stderr or stdout

    if not result.error_message and result.status == "ERROR":
        result.error_message = (
            detailed_logs.get("sby_log")
            or detailed_logs.get("engine_log")
            or stderr
            or stdout
        )

    # Extract elapsed time
    time_match = re.search(r'Elapsed clock time.*?:\s*([\d:.]+)\s*\((\d+)\)', stdout)
    if time_match:
        result.elapsed_seconds = float(time_match.group(2))

    # Extract depth reached
    step_matches = re.findall(r'Checking assertions in step (\d+)', stdout)
    if step_matches:
        result.depth_reached = max(int(s) for s in step_matches) + 1

    # Extract failed assertions
    fail_pattern = re.compile(
        r'failed assertion (\S+) at (\S+):(\d+)(?:\.(\d+))?\s+step (\d+)'
    )
    for m in fail_pattern.finditer(stdout):
        result.failed_assertions.append({
            "name": m.group(1),
            "file": m.group(2),
            "line": int(m.group(3)),
            "step": int(m.group(5)),
        })

    # Find counterexample VCD
    vcd_match = re.search(r'counterexample trace:\s*(\S+)', stdout)
    if vcd_match:
        vcd_path = os.path.join(work_dir, vcd_match.group(1))
        if os.path.exists(vcd_path):
            result.counterexample_vcd = vcd_path

    # Extract engine status
    status_match = re.search(r'engine_\d+.*?returned (\w+)', stdout)
    if status_match:
        engine_status = status_match.group(1).upper()
        if engine_status == "PASS":
            result.status = "PASS"
        elif engine_status in ("FAIL", "FAILED"):
            result.status = "FAIL"

    result.assertion_results = _parse_assertion_results_from_junit(
        detailed_logs.get("junit_xml", "")
    )

    # Fallback: extract per-property rows from engine/sby logs when no JUnit XML.
    if not result.assertion_results:
        result.assertion_results = _parse_assertion_results_from_logs(
            detailed_logs.get("engine_log", "") or
            detailed_logs.get("sby_log", "") or
            stdout
        )

    # Keep failed_assertions aligned with parsed assertion results when possible.
    if result.assertion_results:
        xml_failed = []
        for assertion in result.assertion_results:
            if assertion["status"] != "FAIL":
                continue
            xml_failed.append({
                "name": assertion["name"],
                "file": assertion.get("file", ""),
                "line": assertion.get("line", 0),
                "step": assertion.get("step", 0),
                "message": assertion.get("message", ""),
            })
        if xml_failed:
            result.failed_assertions = xml_failed

    return result


def _collect_sby_logs(work_dir: str) -> tuple[dict[str, str], dict[str, str]]:
    """
    Collect the most relevant staged SymbiYosys logs for API responses.

    We prefer the task directory (e.g. *_bmc) because it contains the
    user-actionable build/prover logs for PASS/FAIL/ERROR runs.
    """
    logs: dict[str, str] = {}
    paths: dict[str, str] = {}

    if not work_dir or not os.path.isdir(work_dir):
        return logs, paths

    task_dirs = []
    for entry in os.scandir(work_dir):
        if entry.is_dir() and os.path.isfile(os.path.join(entry.path, "logfile.txt")):
            task_dirs.append(entry.path)

    task_dir = max(task_dirs, key=os.path.getmtime) if task_dirs else ""
    if task_dir:
        paths["task_dir"] = task_dir
        _read_log_file(task_dir, "logfile.txt", "sby_log", logs, paths)
        _read_log_file(task_dir, os.path.join("engine_0", "logfile.txt"), "engine_log", logs, paths)
        _read_log_file(task_dir, "status", "task_status", logs, paths)
        _read_log_file(task_dir, "status.path", "status_path", logs, paths)

        for marker in ("PASS", "FAIL", "ERROR", "TIMEOUT", "UNKNOWN"):
            marker_path = os.path.join(task_dir, marker)
            if os.path.isfile(marker_path):
                paths["marker_file"] = marker_path
                logs["marker_name"] = marker
                try:
                    logs["marker_contents"] = open(marker_path, "r", encoding="utf-8", errors="replace").read()
                except OSError:
                    pass
                break

        xml_files = [
            name for name in os.listdir(task_dir)
            if name.endswith(".xml") and os.path.isfile(os.path.join(task_dir, name))
        ]
        if xml_files:
            xml_name = sorted(xml_files)[0]
            _read_log_file(task_dir, xml_name, "junit_xml", logs, paths)

    return logs, paths


def _read_log_file(
    root_dir: str,
    relative_path: str,
    key: str,
    logs: dict[str, str],
    paths: dict[str, str],
) -> None:
    """Read a log file if present and store both content and absolute path."""
    full_path = os.path.join(root_dir, relative_path)
    if not os.path.isfile(full_path):
        return

    paths[f"{key}_path"] = full_path
    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            logs[key] = f.read()
    except OSError:
        return


def _parse_assertion_results_from_logs(log_text: str) -> list[dict]:
    """
    Fallback parser: extract per-property rows from sby/smtbmc log text
    when JUnit XML is not available.

    Handles patterns emitted by smtbmc and sby task logs:
      - "Assert cover property <name>"
      - "Assert failed in <name>"
      - "Reached cover point <name>"
      - "assert <name> passed" / "assert <name> failed at step N"
      - "cover <name> reached" / "cover <name> unreachable"
    """
    results: list[dict] = []
    seen: set[str] = set()

    def add(name: str, typ: str, status: str, step: int = 0):
        if name in seen:
            return
        seen.add(name)
        results.append({
            "name": name,
            "status": status,
            "type": typ,
            "location": "",
            "file": "",
            "line": 0,
            "step": step,
            "message": "",
            "tracefile": "",
        })

    # smtbmc: "assert <name> passed" / "assert <name> failed at step N"
    for m in re.finditer(r'\bassert\s+([\w.:/]+)\s+(passed|failed)(?:\s+at\s+step\s+(\d+))?', log_text, re.IGNORECASE):
        status = "PASS" if m.group(2).lower() == "passed" else "FAIL"
        add(m.group(1), "ASSERT", status, int(m.group(3) or 0))

    # smtbmc: "cover <name> reached" / "cover <name> unreachable"
    for m in re.finditer(r'\bcover\s+([\w.:/]+)\s+(reached|unreachable)', log_text, re.IGNORECASE):
        status = "PASS" if m.group(2).lower() == "reached" else "SKIPPED"
        add(m.group(1), "COVER", status)

    # smtbmc: "Assert failed in <hierarchy.name>"
    for m in re.finditer(r'Assert failed in ([\w.:/]+)', log_text):
        add(m.group(1), "ASSERT", "FAIL")

    # smtbmc: "Reached cover point <name>"
    for m in re.finditer(r'Reached cover point ([\w.:/]+)', log_text):
        add(m.group(1), "COVER", "PASS")

    # sby: "Assert cover property <name>" then "Status: PASSED/FAILED"
    # Collect block-level pass/fail
    for m in re.finditer(r'checking\s+(?:property|assertion)\s+([\w.:/]+)[^\n]*\n(?:.*\n)*?.*?status[:\s]+(pass|fail)', log_text, re.IGNORECASE):
        status = "PASS" if "pass" in m.group(2).lower() else "FAIL"
        add(m.group(1), "ASSERT", status)

    return results


def _parse_assertion_results_from_junit(junit_xml: str) -> list[dict]:
    """Parse per-assertion pass/fail/skipped results from SBY's JUnit XML."""
    if not junit_xml.strip():
        return []

    try:
        root = ET.fromstring(junit_xml)
    except ET.ParseError:
        return []

    assertions: list[dict] = []
    for testcase in root.findall(".//testcase"):
        assertion_id = testcase.attrib.get("id", "")
        assertion_type = testcase.attrib.get("type", "")
        if not assertion_id or assertion_type not in {"ASSERT", "ASSUME", "COVER"}:
            continue

        location = testcase.attrib.get("location", "")
        tracefile = testcase.attrib.get("tracefile", "")
        message = ""
        step = 0

        failure = testcase.find("failure")
        error = testcase.find("error")
        skipped = testcase.find("skipped")

        if failure is not None:
            status = "FAIL"
            message = failure.attrib.get("message", "") or (failure.text or "").strip()
        elif error is not None:
            status = "ERROR"
            message = error.attrib.get("message", "") or (error.text or "").strip()
        elif skipped is not None:
            status = "SKIPPED"
            message = skipped.attrib.get("message", "") or (skipped.text or "").strip()
        else:
            status = "PASS"

        step_match = re.search(r"step (\d+)", message)
        if step_match:
            step = int(step_match.group(1))

        file_name = ""
        line = 0
        if location:
            loc_match = re.match(r"([^:]+):(\d+)", location)
            if loc_match:
                file_name = loc_match.group(1)
                line = int(loc_match.group(2))

        assertions.append({
            "name": assertion_id,
            "status": status,
            "type": assertion_type,
            "location": location,
            "file": file_name,
            "line": line,
            "step": step,
            "message": message,
            "tracefile": tracefile,
        })

    return assertions
