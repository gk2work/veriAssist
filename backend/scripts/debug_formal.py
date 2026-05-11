#!/usr/bin/env python3
"""Quick debug: inspect lowered RTL, generated sby, and actual sby error."""

import sys, os, subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.sva_parser import parse_sva, format_parsed_summary
from app.services.sva_lowering import SVALoweringEngine
from app.services.sby_generator import quick_generate
from app.services.formal_service import FormalService

AXI_DUT = """
module axi_slave (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        awvalid,
    output reg         awready
);
    reg [3:0] counter;
    always @(posedge clk) begin
        if (!rst_n) begin
            awready <= 0;
            counter <= 0;
        end else begin
            if (awvalid && !awready) begin
                counter <= counter + 1;
                if (counter >= 3)
                    awready <= 1;
            end else begin
                awready <= 0;
                counter <= 0;
            end
        end
    end
endmodule
"""

AXI_SVA = """
module axi_formal_checker (
    input logic        clk,
    input logic        rst_n,
    input logic        awvalid,
    input logic        awready
);
    default clocking cb @(posedge clk); endclocking
    default disable iff (!rst_n);

    property p_awready_response;
        awvalid && !awready |=> awvalid;
    endproperty

    assert_awready : assert property (p_awready_response);
    cover_awready  : cover property (p_awready_response);
endmodule
"""

# Step 1: Parse
print("=" * 60)
print("STEP 1: PARSE")
print("=" * 60)
parsed = parse_sva(AXI_SVA)
print(format_parsed_summary(parsed))

# Step 2: Lower
print("\n" + "=" * 60)
print("STEP 2: LOWERED RTL")
print("=" * 60)
engine = SVALoweringEngine()
lowered = engine.lower(parsed)
print(lowered)

# Step 3: Generate sby project
print("\n" + "=" * 60)
print("STEP 3: SBY PROJECT")
print("=" * 60)
project = quick_generate(
    sva_code=AXI_SVA,
    dut_code=AXI_DUT,
    dut_filename="axi_slave.sv",
    dut_top="axi_slave",
    mode="bmc",
    depth=15,
    project_name="debug_axi",
)
print(f"Work dir: {project.work_dir}")
print(f"SBY file: {project.sby_file}")

# Show all generated files
work = Path(project.work_dir)
print("\nGenerated files:")
for f in sorted(work.rglob("*")):
    if f.is_file():
        print(f"  {f.relative_to(work)}")

# Show .sby content
print("\n--- .sby content ---")
print(Path(project.sby_file).read_text())

# Show wrapper if exists
wrapper = work / "src" / "formal_wrapper.sv"
if wrapper.exists():
    print("--- formal_wrapper.sv ---")
    print(wrapper.read_text())

# Show monitor
for f in (work / "src").iterdir():
    if "monitor" in f.name:
        print(f"--- {f.name} ---")
        print(f.read_text())

# Step 4: Try running sby
print("\n" + "=" * 60)
print("STEP 4: RUN SBY")
print("=" * 60)
try:
    proc = subprocess.run(
        ["sby", "-f", project.sby_file],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=project.work_dir,
    )
    print(f"Return code: {proc.returncode}")
    print(f"\n--- STDOUT ---")
    print(proc.stdout)
    if proc.stderr:
        print(f"\n--- STDERR ---")
        print(proc.stderr)
except Exception as e:
    print(f"ERROR: {e}")