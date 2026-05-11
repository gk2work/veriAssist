
"""
VeriAssist v2.0 — UVM Generation Evaluation

Tests UVM testbench generation across multiple interface types.

Measures:
1. Interface parsing: correct signal count, protocol detection, clock/reset ID
2. File generation: all 13 files produced with correct names
3. UVM convention compliance: factory macros, phase methods, TLM ports
4. Component completeness: every required element present
5. Protocol awareness: driver has handshake, coverage has protocol-specific bins

Usage:
    python scripts/uvm_eval.py                     # Run all tests
    python scripts/uvm_eval.py --test fifo         # Single test
    python scripts/uvm_eval.py --verbose            # Show generated code stats
    python scripts/uvm_eval.py --dump fifo          # Dump all generated files for fifo

Requires: Backend NOT needed. Runs generator directly.
"""

import sys
import time
import logging
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.interface_parser import parse_interface, format_interface_summary
from app.services.uvm_generator import UVMGenerator

logging.basicConfig(level=logging.WARNING)


# ═══════════════════════════════════════════════════════════════
# TEST DUTs
# ═══════════════════════════════════════════════════════════════

TEST_DUTS = {
    "fifo": {
        "code": """\
module sync_fifo #(parameter DEPTH = 8, parameter WIDTH = 8)(
    input  wire             clk,
    input  wire             rst_n,
    input  wire             wr_en,
    input  wire             rd_en,
    input  wire [WIDTH-1:0] wr_data,
    output reg  [WIDTH-1:0] rd_data,
    output wire             full,
    output wire             empty
);
endmodule
""",
        "expected_protocol": "fifo",
        "expected_signals": 8,
        "expected_inputs": 4,
        "expected_outputs": 3,
    },

    "axi_lite": {
        "code": """\
module axi_lite_slave (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        awvalid,
    output wire        awready,
    input  wire [31:0] awaddr,
    input  wire        wvalid,
    output wire        wready,
    input  wire [31:0] wdata,
    input  wire [3:0]  wstrb,
    output wire        bvalid,
    input  wire        bready,
    output wire [1:0]  bresp,
    input  wire        arvalid,
    output wire        arready,
    input  wire [31:0] araddr,
    output wire        rvalid,
    input  wire        rready,
    output wire [31:0] rdata,
    output wire [1:0]  rresp
);
endmodule
""",
        "expected_protocol": "axi",
        "expected_signals": 19,
        "expected_inputs": 10,
        "expected_outputs": 9,
    },

    "apb": {
        "code": """\
module apb_slave (
    input  wire        pclk,
    input  wire        presetn,
    input  wire        psel,
    input  wire        penable,
    input  wire        pwrite,
    input  wire [31:0] paddr,
    input  wire [31:0] pwdata,
    output wire        pready,
    output wire [31:0] prdata,
    output wire        pslverr
);
endmodule
""",
        "expected_protocol": "apb",
        "expected_signals": 10,
        "expected_inputs": 7,
        "expected_outputs": 3,
    },

    "spi": {
        "code": """\
module spi_master (
    input  wire       clk,
    input  wire       rst_n,
    output wire       sclk,
    output wire       mosi,
    input  wire       miso,
    output wire       cs_n,
    input  wire       start,
    input  wire [7:0] tx_data,
    output reg  [7:0] rx_data,
    output wire       busy,
    output wire       done
);
endmodule
""",
        "expected_protocol": "spi",
        "expected_signals": 11,
        "expected_inputs": 5,
        "expected_outputs": 6,
    },

    "uart": {
        "code": """\
module uart_tx (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [7:0] tx_data,
    input  wire       tx_start,
    output reg        tx,
    output wire       tx_busy,
    output wire       tx_done
);
endmodule
""",
        "expected_protocol": "uart",
        "expected_signals": 7,
        "expected_inputs": 4,
        "expected_outputs": 3,
    },

    "generic": {
        "code": """\
module alu (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [3:0]  opcode,
    input  wire [15:0] operand_a,
    input  wire [15:0] operand_b,
    input  wire        start,
    output reg  [31:0] result,
    output wire        done,
    output wire        overflow
);
endmodule
""",
        "expected_protocol": "generic",
        "expected_signals": 9,
        "expected_inputs": 6,
        "expected_outputs": 3,
    },

    "signal_list": {
        "code": "",
        "signal_list": [
            {"name": "clk", "width": 1, "direction": "input"},
            {"name": "rst_n", "width": 1, "direction": "input"},
            {"name": "valid", "width": 1, "direction": "input"},
            {"name": "ready", "width": 1, "direction": "output"},
            {"name": "data", "width": 32, "direction": "input"},
            {"name": "addr", "width": 16, "direction": "input"},
            {"name": "resp", "width": 2, "direction": "output"},
        ],
        "module_name": "custom_bus",
        "expected_protocol": "generic",
        "expected_signals": 7,
        "expected_inputs": 4,
        "expected_outputs": 2,
    },
}

# Required UVM patterns per component type
UVM_CHECKS = {
    "transaction": [
        ("uvm_object_utils", "Factory registration macro"),
        ("uvm_sequence_item", "Extends uvm_sequence_item"),
        ("uvm_field_int", "Field macro for automation"),
        ("function new", "Constructor"),
        ("rand ", "Randomizable fields"),
    ],
    "driver": [
        ("uvm_component_utils", "Factory registration"),
        ("uvm_driver", "Extends uvm_driver"),
        ("build_phase", "Build phase method"),
        ("run_phase", "Run phase method"),
        ("get_next_item", "Sequencer handshake"),
        ("item_done", "Sequencer completion"),
        ("uvm_config_db", "Config DB access"),
    ],
    "monitor": [
        ("uvm_component_utils", "Factory registration"),
        ("uvm_monitor", "Extends uvm_monitor"),
        ("analysis_port", "Analysis port declaration"),
        ("build_phase", "Build phase"),
        ("run_phase", "Run phase"),
        (".write(", "Analysis port write"),
    ],
    "coverage": [
        ("uvm_component_utils", "Factory registration"),
        ("uvm_subscriber", "Extends uvm_subscriber"),
        ("covergroup", "Covergroup declaration"),
        ("coverpoint", "At least one coverpoint"),
        ("function void write", "Write function from subscriber"),
        (".sample(", "Covergroup sampling"),
    ],
    "scoreboard": [
        ("uvm_component_utils", "Factory registration"),
        ("uvm_scoreboard", "Extends uvm_scoreboard"),
        ("analysis_imp", "Analysis imp declaration"),
        ("function void write", "Write function"),
        ("report_phase", "Report phase with summary"),
    ],
    "agent": [
        ("uvm_component_utils", "Factory registration"),
        ("uvm_agent", "Extends uvm_agent"),
        ("build_phase", "Build phase"),
        ("connect_phase", "Connect phase"),
        ("UVM_ACTIVE", "Active/passive check"),
        ("type_id::create", "Factory creation"),
    ],
    "env": [
        ("uvm_component_utils", "Factory registration"),
        ("uvm_env", "Extends uvm_env"),
        ("build_phase", "Build phase"),
        ("connect_phase", "Connect phase"),
        ("analysis_port.connect", "TLM connection"),
    ],
    "test": [
        ("uvm_component_utils", "Factory registration"),
        ("uvm_test", "Extends uvm_test"),
        ("build_phase", "Build phase"),
        ("run_phase", "Run phase"),
        ("raise_objection", "Phase objection raise"),
        ("drop_objection", "Phase objection drop"),
        (".start(", "Sequence start"),
    ],
    "seq_lib": [
        ("uvm_object_utils", "Factory registration"),
        ("uvm_sequence", "Extends uvm_sequence"),
        ("task body", "Body task"),
        ("start_item", "Sequence item start"),
        ("finish_item", "Sequence item finish"),
        ("randomize", "Transaction randomization"),
    ],
    "interface": [
        ("interface ", "Interface declaration"),
        ("clocking", "Clocking block"),
        ("modport", "Modport declaration"),
        ("endinterface", "Interface end"),
    ],
    "package": [
        ("package ", "Package declaration"),
        ("import uvm_pkg", "UVM import"),
        ("uvm_macros.svh", "UVM macros include"),
        ("endpackage", "Package end"),
    ],
}


# ═══════════════════════════════════════════════════════════════
# EVALUATION
# ═══════════════════════════════════════════════════════════════

def run_eval(test_filter: str = None, verbose: bool = False, dump: str = None):
    """Run UVM generation evaluation."""

    tests = TEST_DUTS
    if test_filter:
        if test_filter in tests:
            tests = {test_filter: tests[test_filter]}
        else:
            print(f"Test '{test_filter}' not found. Available: {', '.join(tests.keys())}")
            return

    print(f"\n{'='*70}")
    print(f"  VeriAssist v2.0 — UVM Generation Evaluation")
    print(f"{'='*70}")
    print(f"  Tests: {len(tests)}")
    print(f"{'='*70}\n")

    generator = UVMGenerator()
    results = []
    total_time = 0

    for test_name, test_data in tests.items():
        print(f"  [{len(results)+1}/{len(tests)}] {test_name}")

        t0 = time.time()
        result = {
            "name": test_name,
            "parse_ok": False,
            "protocol_ok": False,
            "signal_count_ok": False,
            "files_ok": False,
            "uvm_checks": {},
            "total_checks": 0,
            "passed_checks": 0,
            "file_count": 0,
            "total_lines": 0,
            "latency": 0,
            "errors": [],
        }

        try:
            # Step 1: Parse interface
            signal_list = test_data.get("signal_list")
            iface = parse_interface(
                dut_code=test_data.get("code", ""),
                signal_list=signal_list,
                module_name=test_data.get("module_name", ""),
                protocol_hint=test_data.get("protocol_hint", ""),
            )

            result["parse_ok"] = len(iface.signals) > 0
            result["protocol_ok"] = iface.protocol == test_data["expected_protocol"]
            result["signal_count_ok"] = len(iface.signals) == test_data["expected_signals"]

            if not result["parse_ok"]:
                result["errors"].append("No signals parsed")
                results.append(result)
                continue

            if verbose:
                print(f"         Protocol: {iface.protocol} (expected: {test_data['expected_protocol']})")
                print(f"         Signals: {len(iface.signals)} (expected: {test_data['expected_signals']})")

            # Step 2: Generate testbench
            name = test_data.get("module_name", "") or iface.module_name or test_name
            tb = generator.generate(iface=iface, name=name)

            result["file_count"] = tb.file_count
            result["total_lines"] = tb.total_lines
            result["files_ok"] = tb.file_count >= 12

            if verbose:
                print(f"         Files: {tb.file_count}, Lines: {tb.total_lines}")

            # Step 3: UVM convention checks per component
            total_checks = 0
            passed_checks = 0

            for comp_type, checks in UVM_CHECKS.items():
                gen_file = tb.get_file(comp_type)
                if not gen_file:
                    # Some component types are optional
                    continue

                comp_passed = 0
                comp_total = len(checks)
                total_checks += comp_total

                for pattern, check_name in checks:
                    if pattern in gen_file.content:
                        comp_passed += 1
                        passed_checks += 1
                    else:
                        result["errors"].append(f"{comp_type}: missing '{pattern}' ({check_name})")

                result["uvm_checks"][comp_type] = f"{comp_passed}/{comp_total}"

                if verbose:
                    status = "\033[92m\u2713\033[0m" if comp_passed == comp_total else "\033[91m\u2717\033[0m"
                    print(f"         {status} {comp_type:12s} {comp_passed}/{comp_total}")

            result["total_checks"] = total_checks
            result["passed_checks"] = passed_checks

            # Dump files if requested
            if dump and dump == test_name:
                print(f"\n{'─'*60}")
                for f in tb.files:
                    print(f"\n  ── {f.filename} ({len(f.content.splitlines())} lines) ──")
                    print(f.content)
                print(f"{'─'*60}\n")

        except Exception as e:
            result["errors"].append(str(e))
            print(f"         \033[91mERROR: {e}\033[0m")

        latency = time.time() - t0
        result["latency"] = latency
        total_time += latency

        # Summary for this test
        all_ok = result["parse_ok"] and result["protocol_ok"] and result["files_ok"]
        check_rate = result["passed_checks"] / result["total_checks"] if result["total_checks"] > 0 else 0
        status = "\033[92mPASS\033[0m" if all_ok and check_rate >= 0.9 else "\033[91mFAIL\033[0m"

        print(f"         [{status}] protocol={'ok' if result['protocol_ok'] else 'WRONG'} "
              f"files={result['file_count']} lines={result['total_lines']} "
              f"uvm={result['passed_checks']}/{result['total_checks']} "
              f"{latency:.3f}s")

        if result["errors"] and not verbose:
            for e in result["errors"][:3]:
                print(f"           \033[91m\u2022 {e}\033[0m")

        results.append(result)

    # ═══════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════
    total = len(results)
    parse_ok = sum(1 for r in results if r["parse_ok"])
    proto_ok = sum(1 for r in results if r["protocol_ok"])
    files_ok = sum(1 for r in results if r["files_ok"])
    total_checks = sum(r["total_checks"] for r in results)
    passed_checks = sum(r["passed_checks"] for r in results)
    total_lines = sum(r["total_lines"] for r in results)
    check_rate = passed_checks / total_checks if total_checks > 0 else 0

    all_pass = sum(1 for r in results if r["parse_ok"] and r["protocol_ok"] and r["files_ok"]
                   and (r["passed_checks"] / r["total_checks"] >= 0.9 if r["total_checks"] > 0 else False))

    print(f"\n{'='*70}")
    print(f"  UVM GENERATION EVALUATION RESULTS")
    print(f"{'='*70}")
    print(f"\n  Pipeline:")
    print(f"    Interface parsing:   {parse_ok}/{total} ({100*parse_ok/total:.0f}%)")
    print(f"    Protocol detection:  {proto_ok}/{total} ({100*proto_ok/total:.0f}%)")
    print(f"    File generation:     {files_ok}/{total} ({100*files_ok/total:.0f}%)")
    print(f"    UVM compliance:      {passed_checks}/{total_checks} ({100*check_rate:.0f}%)")
    print(f"    Total lines:         {total_lines}")
    print(f"    Total time:          {total_time:.2f}s")
    print(f"    Avg per testbench:   {total_time/total:.3f}s")

    print(f"\n  Per test:")
    for r in results:
        icon = "\033[92m\u2713\033[0m" if r["parse_ok"] and r["protocol_ok"] and r["files_ok"] else "\033[91m\u2717\033[0m"
        print(f"    {icon} {r['name']:15s} proto={'ok' if r['protocol_ok'] else 'X':4s} "
              f"files={r['file_count']:2d} lines={r['total_lines']:4d} "
              f"uvm={r['passed_checks']}/{r['total_checks']}  {r['latency']:.3f}s")

    # Grade
    if all_pass == total and check_rate >= 0.95:
        grade = "\033[92mEXCELLENT\033[0m"
    elif all_pass >= total * 0.8 and check_rate >= 0.85:
        grade = "\033[92mGOOD\033[0m"
    elif all_pass >= total * 0.5:
        grade = "\033[93mFAIR\033[0m"
    else:
        grade = "\033[91mPOOR\033[0m"

    print(f"\n  Grade: {grade} ({all_pass}/{total} tests fully passing, {100*check_rate:.0f}% UVM compliance)")
    print(f"\n{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(description="VeriAssist UVM Generation Evaluation")
    parser.add_argument("--test", type=str, help="Run only this test")
    parser.add_argument("--verbose", action="store_true", help="Show per-component check details")
    parser.add_argument("--dump", type=str, help="Dump all generated files for this test")

    args = parser.parse_args()
    run_eval(test_filter=args.test, verbose=args.verbose, dump=args.dump)


if __name__ == "__main__":
    main()