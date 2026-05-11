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
    UUT.u_dut._witness_.anyinit_procdff_401 = 8'b00000000;
    UUT.u_dut._witness_.anyinit_procdff_406 = 1'b0;
    UUT.u_dut._witness_.anyinit_procdff_411 = 5'b00000;
    UUT.u_dut._witness_.anyinit_procdff_416 = 1'b0;
    UUT.u_dut._witness_.anyinit_procdff_422 = 5'b00000;
    UUT.u_dut.mem = 256'b0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000;
    // UUT.u_monitor.$auto$async2sync.\cc:107:execute$459  = 1'b0;
    // UUT.u_monitor.$auto$async2sync.\cc:116:execute$463  = 1'b1;
    UUT.u_monitor._va_ap_fifo_data_after_empty_stage_6 = 1'b0;
    UUT.u_monitor._va_ap_fifo_data_after_empty_trig_7 = 1'b0;
    UUT.u_monitor.wr_data_in_past1 = 8'b10000000;

    // state 0
    PI_rst_n = 1'b0;
    UUT.data_start = 1'b0;
    UUT.rd_en = 1'b0;
    UUT.wr_data = 8'b00000000;
    UUT.wr_en = 1'b0;
  end
  always @(posedge clock) begin
    // state 1
    if (cycle == 0) begin
      PI_rst_n <= 1'b1;
      UUT.data_start <= 1'b0;
      UUT.rd_en <= 1'b0;
      UUT.wr_data <= 8'b00000000;
      UUT.wr_en <= 1'b1;
    end

    // state 2
    if (cycle == 1) begin
      PI_rst_n <= 1'b1;
      UUT.data_start <= 1'b0;
      UUT.rd_en <= 1'b1;
      UUT.wr_data <= 8'b10000000;
      UUT.wr_en <= 1'b0;
    end

    // state 3
    if (cycle == 2) begin
      PI_rst_n <= 1'b1;
      UUT.data_start <= 1'b0;
      UUT.rd_en <= 1'b0;
      UUT.wr_data <= 8'b00000000;
      UUT.wr_en <= 1'b0;
    end

    // state 4
    if (cycle == 3) begin
      PI_rst_n <= 1'b0;
      UUT.data_start <= 1'b0;
      UUT.rd_en <= 1'b0;
      UUT.wr_data <= 8'b00000000;
      UUT.wr_en <= 1'b0;
    end

    genclock <= cycle < 4;
    cycle <= cycle + 1;
  end
endmodule
