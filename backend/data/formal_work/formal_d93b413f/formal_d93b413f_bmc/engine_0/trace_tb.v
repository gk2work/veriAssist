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
  wire [0:0] PI_clk = clock;
  reg [0:0] PI_b;
  reg [0:0] PI_a;
  reg [0:0] PI_rst_n;
  chk UUT (
    .clk(PI_clk),
    .b(PI_b),
    .a(PI_a),
    .rst_n(PI_rst_n)
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
    // UUT.$auto$async2sync.\cc:107:execute$16  = 1'b0;
    // UUT.$auto$async2sync.\cc:116:execute$20  = 1'b1;
    UUT._va_assert_p1_triggered_1 = 1'b1;

    // state 0
    PI_b = 1'b0;
    PI_a = 1'b0;
    PI_rst_n = 1'b1;
  end
  always @(posedge clock) begin
    // state 1
    if (cycle == 0) begin
      PI_b <= 1'b0;
      PI_a <= 1'b0;
      PI_rst_n <= 1'b0;
    end

    genclock <= cycle < 1;
    cycle <= cycle + 1;
  end
endmodule
