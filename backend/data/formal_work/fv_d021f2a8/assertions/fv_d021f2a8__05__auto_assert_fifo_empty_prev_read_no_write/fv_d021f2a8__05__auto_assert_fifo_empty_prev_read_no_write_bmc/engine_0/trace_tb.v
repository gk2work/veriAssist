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
  reg [0:0] PI_rst_n;
  formal_wrapper UUT (
    .clk(PI_clk),
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
    UUT._va_past_valid = 1'b0;
    UUT.u_dut._witness_.anyinit_procdff_217 = 8'b00000000;
    UUT.u_dut._witness_.anyinit_procdff_222 = 1'b0;
    UUT.u_dut._witness_.anyinit_procdff_227 = 5'b00000;
    UUT.u_dut._witness_.anyinit_procdff_232 = 1'b0;
    UUT.u_dut._witness_.anyinit_procdff_238 = 5'b00000;
    UUT.u_dut.mem = 256'b0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000;
    // UUT.u_monitor.$auto$async2sync.\cc:107:execute$263  = 1'b0;
    // UUT.u_monitor.$auto$async2sync.\cc:116:execute$267  = 1'b1;
    UUT.u_monitor.empty_out_prev = 1'b0;
    UUT.u_monitor.rd_en_in_past1 = 1'b0;
    UUT.u_monitor.wr_en_in_past1 = 1'b0;

    // state 0
    PI_rst_n = 1'b0;
    UUT.rd_en = 1'b0;
    UUT.wr_data = 8'b00000000;
    UUT.wr_en = 1'b0;
  end
  always @(posedge clock) begin
    // state 1
    if (cycle == 0) begin
      PI_rst_n <= 1'b1;
      UUT.rd_en <= 1'b0;
      UUT.wr_data <= 8'b00000000;
      UUT.wr_en <= 1'b0;
    end

    // state 2
    if (cycle == 1) begin
      PI_rst_n <= 1'b1;
      UUT.rd_en <= 1'b0;
      UUT.wr_data <= 8'b00000000;
      UUT.wr_en <= 1'b0;
    end

    genclock <= cycle < 2;
    cycle <= cycle + 1;
  end
endmodule
