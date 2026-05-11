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
    UUT._va_past_valid = 1'b0;
    UUT.u_dut.awready = 1'b0;
    // UUT.u_monitor.$auto$async2sync.\cc:107:execute$34  = 1'b0;
    // UUT.u_monitor.$auto$async2sync.\cc:116:execute$38  = 1'b1;
    UUT.u_monitor._va_assert_must_respond_triggered_1 = 1'b0;

    // state 0
    PI_rst_n = 1'b0;
    UUT.awvalid = 1'b0;
  end
  always @(posedge clock) begin
    // state 1
    if (cycle == 0) begin
      PI_rst_n <= 1'b1;
      UUT.awvalid <= 1'b1;
    end

    // state 2
    if (cycle == 1) begin
      PI_rst_n <= 1'b1;
      UUT.awvalid <= 1'b0;
    end

    // state 3
    if (cycle == 2) begin
      PI_rst_n <= 1'b0;
      UUT.awvalid <= 1'b0;
    end

    genclock <= cycle < 3;
    cycle <= cycle + 1;
  end
endmodule
