`ifndef VERILATOR
module testbench;
  reg [4095:0] vcdfile;
  reg clock;
`else
module testbench(input clock, output reg genclock);
  initial genclock = 1;
`endif
  reg genclock = 1;
  reg [31:0] cycle = 0;
  reg [0:0] PI_rst_n;
  wire [0:0] PI_clk = clock;
  formal_wrapper UUT (
    .rst_n(PI_rst_n),
    .clk(PI_clk)
  );
`ifndef VERILATOR
  initial begin
    if ($value$plusargs("vcd=%s", vcdfile)) begin
      $dumpfile(vcdfile);
      $dumpvars(0, testbench);
    end
    #5 clock = 0;
    while (genclock) begin
      #5 clock = 0;
      #5 clock = 1;
    end
  end
`endif
  initial begin
`ifndef VERILATOR
    #1;
`endif
    UUT.u_dut.awready = 1'b0;
    UUT.u_dut.counter = 4'b0000;
    // UUT.u_monitor.$auto$async2sync.\cc:107:execute$58  = 1'b0;
    // UUT.u_monitor.$auto$async2sync.\cc:116:execute$62  = 1'b1;
    UUT.u_monitor._va_assert_awready_triggered_1 = 1'b1;

    // state 0
    PI_rst_n = 1'b1;
    UUT.awvalid = 1'b0;
  end
  always @(posedge clock) begin
    // state 1
    if (cycle == 0) begin
      PI_rst_n <= 1'b0;
      UUT.awvalid <= 1'b0;
    end

    genclock <= cycle < 1;
    cycle <= cycle + 1;
  end
endmodule
