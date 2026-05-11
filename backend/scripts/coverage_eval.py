#!/usr/bin/env python3
"""
VeriAssist v2.0 — Coverage Advisor Evaluation

Tests coverage analysis and generation across multiple DUTs.

Measures:
1. FSM detection: correct state count, transition count
2. Opportunity quality: protocol-specific gaps identified
3. Covergroup correctness: valid SV syntax, proper bins
4. Sequence recommendations: actionable sequences generated
5. Protocol detection accuracy

Usage:
    python scripts/coverage_eval.py                  # Run all tests
    python scripts/coverage_eval.py --test fsm       # Single test
    python scripts/coverage_eval.py --verbose         # Show details
    python scripts/coverage_eval.py --dump fsm        # Dump generated coverage

Requires: Backend NOT needed. Runs directly.
"""

import sys
import time
import logging
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.interface_parser import parse_interface
from app.services.coverage_analyzer import coverage_analyzer, format_analysis_summary
from app.services.coverage_generator import coverage_generator

logging.basicConfig(level=logging.WARNING)


# ═══════════════════════════════════════════════════════════════
# TEST DUTS
# ═══════════════════════════════════════════════════════════════

TEST_DUTS = {
    "fsm": {
        "code": """\
module protocol_fsm (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       start,
    input  wire       data_valid,
    input  wire       resp_ok,
    input  wire       error,
    output reg  [2:0] state
);
    localparam IDLE = 3'd0;
    localparam ADDR = 3'd1;
    localparam DATA = 3'd2;
    localparam RESP = 3'd3;
    localparam DONE = 3'd4;

    always @(posedge clk) begin
        if (!rst_n)
            state <= IDLE;
        else begin
            case (state)
                IDLE: if (start) state <= ADDR;
                ADDR: state <= DATA;
                DATA: if (data_valid) state <= RESP;
                RESP: if (resp_ok) state <= DONE;
                DONE: state <= IDLE;
                default: state <= IDLE;
            endcase
        end
    end
endmodule
""",
        "expected_protocol": "generic",
        "expected_fsm_count": 1,
        "expected_states_min": 5,
        "expected_transitions_min": 5,
        "required_categories": ["fsm_state", "fsm_transition"],
    },

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
    reg [WIDTH-1:0] mem [0:DEPTH-1];
    reg [$clog2(DEPTH):0] count;
    reg [$clog2(DEPTH)-1:0] wr_ptr, rd_ptr;
    assign full  = (count == DEPTH);
    assign empty = (count == 0);
    always @(posedge clk) begin
        if (!rst_n) begin
            count <= 0; wr_ptr <= 0; rd_ptr <= 0;
        end else begin
            if (wr_en && !full) begin
                mem[wr_ptr] <= wr_data; wr_ptr <= wr_ptr + 1; count <= count + 1;
            end
            if (rd_en && !empty) begin
                rd_data <= mem[rd_ptr]; rd_ptr <= rd_ptr + 1; count <= count - 1;
            end
        end
    end
endmodule
""",
        "expected_protocol": "fifo",
        "expected_fsm_count": 0,
        "expected_states_min": 0,
        "expected_transitions_min": 0,
        "required_categories": ["protocol_specific", "data_boundary", "control_cross"],
    },

    "axi_lite": {
        "code": """\
module axi_lite_slave (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        awvalid,
    output reg         awready,
    input  wire [31:0] awaddr,
    input  wire        wvalid,
    output reg         wready,
    input  wire [31:0] wdata,
    input  wire [3:0]  wstrb,
    output reg         bvalid,
    input  wire        bready,
    output reg  [1:0]  bresp,
    input  wire        arvalid,
    output reg         arready,
    input  wire [31:0] araddr,
    output reg         rvalid,
    input  wire        rready,
    output reg  [31:0] rdata,
    output reg  [1:0]  rresp
);
    always @(posedge clk) begin
        if (!rst_n) begin
            awready <= 0; wready <= 0; bvalid <= 0; bresp <= 0;
            arready <= 0; rvalid <= 0; rdata <= 0; rresp <= 0;
        end
    end
endmodule
""",
        "expected_protocol": "axi",
        "expected_fsm_count": 0,
        "expected_states_min": 0,
        "expected_transitions_min": 0,
        "required_categories": ["protocol_specific", "data_boundary"],
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
    output reg         pready,
    output reg  [31:0] prdata,
    output reg         pslverr
);
    always @(posedge pclk) begin
        if (!presetn) begin
            pready <= 0; prdata <= 0; pslverr <= 0;
        end
    end
endmodule
""",
        "expected_protocol": "apb",
        "expected_fsm_count": 0,
        "expected_states_min": 0,
        "expected_transitions_min": 0,
        "required_categories": ["protocol_specific"],
    },

    "fsm_no_default": {
        "code": """\
module buggy_fsm (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       go,
    output reg  [1:0] state
);
    localparam S0 = 2'd0;
    localparam S1 = 2'd1;
    localparam S2 = 2'd2;

    always @(posedge clk) begin
        if (!rst_n)
            state <= S0;
        else begin
            case (state)
                S0: if (go) state <= S1;
                S1: state <= S2;
                S2: state <= S0;
            endcase
        end
    end
endmodule
""",
        "expected_protocol": "generic",
        "expected_fsm_count": 1,
        "expected_states_min": 3,
        "expected_transitions_min": 3,
        "required_categories": ["fsm_state"],
    },
}


# ═══════════════════════════════════════════════════════════════
# EVALUATION
# ═══════════════════════════════════════════════════════════════

def run_eval(test_filter: str = None, verbose: bool = False, dump: str = None):
    """Run coverage advisor evaluation."""

    tests = TEST_DUTS
    if test_filter:
        if test_filter in tests:
            tests = {test_filter: tests[test_filter]}
        else:
            print(f"Test '{test_filter}' not found. Available: {', '.join(tests.keys())}")
            return

    print(f"\n{'='*70}")
    print(f"  VeriAssist v2.0 — Coverage Advisor Evaluation")
    print(f"{'='*70}")
    print(f"  Tests: {len(tests)}")
    print(f"{'='*70}\n")

    results = []
    total_time = 0

    for test_name, test_data in tests.items():
        print(f"  [{len(results)+1}/{len(tests)}] {test_name}")
        t0 = time.time()

        result = {
            "name": test_name,
            "protocol_ok": False,
            "fsm_ok": False,
            "categories_ok": False,
            "covergroup_ok": False,
            "recommendations_ok": False,
            "opportunity_count": 0,
            "coverpoint_count": 0,
            "cross_count": 0,
            "recommendation_count": 0,
            "errors": [],
            "latency": 0,
        }

        try:
            # Parse interface
            iface = parse_interface(
                dut_code=test_data["code"],
                protocol_hint=test_data.get("protocol_hint", ""),
            )

            # Check protocol
            result["protocol_ok"] = iface.protocol == test_data["expected_protocol"]

            # Analyze
            analysis = coverage_analyzer.analyze(
                dut_code=test_data["code"],
                iface=iface,
            )
            result["opportunity_count"] = analysis.total_opportunities

            # Check FSM detection
            fsm_count_ok = len(analysis.fsms) >= test_data["expected_fsm_count"]
            states_ok = True
            transitions_ok = True

            if test_data["expected_fsm_count"] > 0 and analysis.fsms:
                fsm = analysis.fsms[0]
                states_ok = len(fsm.states) >= test_data["expected_states_min"]
                transitions_ok = len(fsm.transitions) >= test_data["expected_transitions_min"]

                if verbose:
                    print(f"         FSM: {fsm.state_reg}, {len(fsm.states)} states, {len(fsm.transitions)} transitions, default={fsm.has_default}")

            result["fsm_ok"] = fsm_count_ok and states_ok and transitions_ok

            if not fsm_count_ok:
                result["errors"].append(f"FSM count: expected >= {test_data['expected_fsm_count']}, got {len(analysis.fsms)}")

            # Check required categories present
            found_categories = set(opp.category for opp in analysis.opportunities)
            required = set(test_data["required_categories"])
            missing = required - found_categories
            result["categories_ok"] = len(missing) == 0

            if missing:
                result["errors"].append(f"Missing categories: {missing}")

            if verbose:
                print(f"         Protocol: {iface.protocol} (expected: {test_data['expected_protocol']})")
                print(f"         Opportunities: {analysis.total_opportunities} (H:{analysis.high_priority} M:{analysis.medium_priority} L:{analysis.low_priority})")
                print(f"         Categories: {sorted(found_categories)}")

            # Generate coverage model
            model = coverage_generator.generate(
                dut_code=test_data["code"],
                iface=iface,
                name=iface.module_name or test_name,
            )

            result["coverpoint_count"] = model.total_coverpoints
            result["cross_count"] = model.total_crosses
            result["recommendation_count"] = len(model.recommendations)

            # Check covergroup validity
            cg = model.covergroup_code
            has_covergroup = "covergroup" in cg and "endgroup" in cg
            has_coverpoints = "coverpoint" in cg
            has_bins = "bins" in cg
            result["covergroup_ok"] = has_covergroup and has_coverpoints and has_bins

            if not has_covergroup:
                result["errors"].append("Covergroup missing covergroup/endgroup")
            if not has_coverpoints:
                result["errors"].append("No coverpoints in covergroup")

            # Check recommendations
            result["recommendations_ok"] = len(model.recommendations) >= 1

            if verbose:
                print(f"         Coverpoints: {model.total_coverpoints}, Crosses: {model.total_crosses}")
                print(f"         Recommendations: {len(model.recommendations)}")
                for rec in model.recommendations[:3]:
                    print(f"           [{rec.priority}] {rec.name}: {rec.description[:60]}")

            # Dump if requested
            if dump and dump == test_name:
                print(f"\n{'─'*60}")
                print(f"  ── Covergroup Code ──")
                print(model.covergroup_code)
                print(f"\n  ── Subscriber Code ──")
                print(model.subscriber_code)
                print(f"\n  ── Recommendations ──")
                for rec in model.recommendations:
                    print(f"\n  [{rec.priority}] {rec.name}")
                    print(f"  {rec.description}")
                    if rec.sequence_code:
                        print(f"  Code:")
                        print(rec.sequence_code)
                print(f"\n  ── Checklist ({len(model.checklist)} items) ──")
                for item in model.checklist[:10]:
                    print(f"  [{item['priority']:6s}] {item['item']}")
                print(f"{'─'*60}\n")

        except Exception as e:
            result["errors"].append(str(e))
            print(f"         \033[91mERROR: {e}\033[0m")

        latency = time.time() - t0
        result["latency"] = latency
        total_time += latency

        # Summary for this test
        all_ok = (result["protocol_ok"] and result["fsm_ok"] and
                  result["categories_ok"] and result["covergroup_ok"] and
                  result["recommendations_ok"])
        status = "\033[92mPASS\033[0m" if all_ok else "\033[91mFAIL\033[0m"

        print(f"         [{status}] proto={'ok' if result['protocol_ok'] else 'X'} "
              f"fsm={'ok' if result['fsm_ok'] else 'X'} "
              f"cats={'ok' if result['categories_ok'] else 'X'} "
              f"cg={'ok' if result['covergroup_ok'] else 'X'} "
              f"recs={result['recommendation_count']} "
              f"opp={result['opportunity_count']} "
              f"{latency:.3f}s")

        if result["errors"] and not verbose:
            for e in result["errors"][:2]:
                print(f"           \033[91m\u2022 {e}\033[0m")

        results.append(result)

    # ═══════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════
    total = len(results)
    proto_ok = sum(1 for r in results if r["protocol_ok"])
    fsm_ok = sum(1 for r in results if r["fsm_ok"])
    cats_ok = sum(1 for r in results if r["categories_ok"])
    cg_ok = sum(1 for r in results if r["covergroup_ok"])
    recs_ok = sum(1 for r in results if r["recommendations_ok"])
    all_pass = sum(1 for r in results if r["protocol_ok"] and r["fsm_ok"] and
                   r["categories_ok"] and r["covergroup_ok"] and r["recommendations_ok"])
    total_opps = sum(r["opportunity_count"] for r in results)
    total_cps = sum(r["coverpoint_count"] for r in results)

    print(f"\n{'='*70}")
    print(f"  COVERAGE ADVISOR EVALUATION RESULTS")
    print(f"{'='*70}")
    print(f"\n  Pipeline:")
    print(f"    Protocol detection:    {proto_ok}/{total} ({100*proto_ok/total:.0f}%)")
    print(f"    FSM detection:         {fsm_ok}/{total} ({100*fsm_ok/total:.0f}%)")
    print(f"    Category coverage:     {cats_ok}/{total} ({100*cats_ok/total:.0f}%)")
    print(f"    Covergroup quality:    {cg_ok}/{total} ({100*cg_ok/total:.0f}%)")
    print(f"    Recommendations:       {recs_ok}/{total} ({100*recs_ok/total:.0f}%)")
    print(f"    Total opportunities:   {total_opps}")
    print(f"    Total coverpoints:     {total_cps}")
    print(f"    Total time:            {total_time:.2f}s")

    print(f"\n  Per test:")
    for r in results:
        all_ok = r["protocol_ok"] and r["fsm_ok"] and r["categories_ok"] and r["covergroup_ok"] and r["recommendations_ok"]
        icon = "\033[92m\u2713\033[0m" if all_ok else "\033[91m\u2717\033[0m"
        print(f"    {icon} {r['name']:15s} opp={r['opportunity_count']:2d} cp={r['coverpoint_count']:2d} "
              f"cx={r['cross_count']:1d} recs={r['recommendation_count']:1d}  {r['latency']:.3f}s")

    # Grade
    if all_pass == total:
        grade = "\033[92mEXCELLENT\033[0m"
    elif all_pass >= total * 0.8:
        grade = "\033[92mGOOD\033[0m"
    elif all_pass >= total * 0.5:
        grade = "\033[93mFAIR\033[0m"
    else:
        grade = "\033[91mPOOR\033[0m"

    print(f"\n  Grade: {grade} ({all_pass}/{total} tests fully passing)")
    print(f"\n{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(description="VeriAssist Coverage Advisor Evaluation")
    parser.add_argument("--test", type=str, help="Run only this test")
    parser.add_argument("--verbose", action="store_true", help="Show detailed analysis")
    parser.add_argument("--dump", type=str, help="Dump generated coverage for this test")

    args = parser.parse_args()
    run_eval(test_filter=args.test, verbose=args.verbose, dump=args.dump)


if __name__ == "__main__":
    main()