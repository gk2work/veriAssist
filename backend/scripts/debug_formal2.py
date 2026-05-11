#!/usr/bin/env python3
"""Debug the two remaining test failures."""
import sys, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.formal_service import FormalService

service = FormalService()

# ── Debug AXI correct ──
print("=" * 60)
print("DEBUG: AXI correct (expected PASS, got FAIL)")
print("=" * 60)

job = service.run_formal(
    sva_code='''
module axi_formal_checker (
    input logic clk, input logic rst_n,
    input logic awvalid, input logic awready
);
    default clocking cb @(posedge clk); endclocking
    default disable iff (!rst_n);
    property p_test; awready |-> awvalid; endproperty
    assert_test : assert property (p_test);
endmodule
''',
    dut_code='''
module axi_slave (
    input wire clk, input wire rst_n,
    input wire awvalid, output reg awready
);
    reg [3:0] counter;
    always @(posedge clk) begin
        if (!rst_n) begin awready <= 0; counter <= 0; end
        else begin
            if (awvalid && !awready) begin
                counter <= counter + 1;
                if (counter >= 3) awready <= 1;
            end else begin awready <= 0; counter <= 0; end
        end
    end
endmodule
''',
    dut_filename="axi.sv", dut_top="axi_slave",
    mode="bmc", depth=15, project_name="debug_axi2",
)

print(f"Status: {job.result.status}")
print(f"Depth: {job.result.depth_reached}")
if job.result.failed_assertions:
    for fa in job.result.failed_assertions:
        print(f"  FAIL: {fa}")

# Show wrapper
w = Path(job.sby_project_dir) / "src" / "formal_wrapper.sv"
if w.exists():
    print(f"\n--- wrapper ---")
    print(w.read_text())

# Show sby output last 15 lines
lines = job.result.engine_output.strip().split("\n")
print(f"\n--- sby output (last 15 lines) ---")
for l in lines[-15:]:
    print(l)

# ── Debug FIFO buggy ──
print("\n" + "=" * 60)
print("DEBUG: FIFO buggy (expected FAIL, got PASS)")
print("=" * 60)

job2 = service.run_formal(
    sva_code='''
module fifo_formal_checker (
    input logic clk, input logic rst_n,
    input logic wr_en, input logic full, input logic empty,
    input logic rd_en, input logic [3:0] count
);
    default clocking cb @(posedge clk); endclocking
    default disable iff (!rst_n);
    property p_count_bounded; (count <= 8); endproperty
    assert_count : assert property (p_count_bounded);
endmodule
''',
    dut_code='''
module sync_fifo #(parameter DEPTH = 8, parameter WIDTH = 8)(
    input wire clk, input wire rst_n,
    input wire wr_en, input wire [WIDTH-1:0] wr_data,
    input wire rd_en, output reg [WIDTH-1:0] rd_data,
    output wire full, output wire empty,
    output reg [$clog2(DEPTH):0] count
);
    reg [WIDTH-1:0] mem [0:DEPTH-1];
    reg [$clog2(DEPTH)-1:0] wr_ptr, rd_ptr;
    assign full = (count == DEPTH);
    assign empty = (count == 0);
    always @(posedge clk) begin
        if (!rst_n) begin wr_ptr <= 0; end
        else if (wr_en) begin mem[wr_ptr] <= wr_data; wr_ptr <= wr_ptr + 1; end
    end
    always @(posedge clk) begin
        if (!rst_n) begin rd_ptr <= 0; rd_data <= 0; end
        else if (rd_en && !empty) begin rd_data <= mem[rd_ptr]; rd_ptr <= rd_ptr + 1; end
    end
    always @(posedge clk) begin
        if (!rst_n) count <= 0;
        else case ({wr_en, rd_en && !empty})
            2\'b10: count <= count + 1;
            2\'b01: count <= count - 1;
            default: count <= count;
        endcase
    end
endmodule
''',
    dut_filename="fifo.sv", dut_top="sync_fifo",
    mode="bmc", depth=20, project_name="debug_fifo2",
)

print(f"Status: {job2.result.status}")
print(f"Depth: {job2.result.depth_reached}")

# Show wrapper
w2 = Path(job2.sby_project_dir) / "src" / "formal_wrapper.sv"
if w2.exists():
    print(f"\n--- wrapper ---")
    print(w2.read_text())

lines2 = job2.result.engine_output.strip().split("\n")
print(f"\n--- sby output (last 15 lines) ---")
for l in lines2[-15:]:
    print(l)