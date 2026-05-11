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
    UUT.u_dut.count = 4'b1100;
    UUT.u_dut.rd_data = 8'b00000000;
    UUT.u_dut.rd_ptr = 3'b000;
    UUT.u_dut.wr_ptr = 3'b000;
    // UUT.u_monitor.$auto$async2sync.\cc:107:execute$112  = 1'b0;
    // UUT.u_monitor.$auto$async2sync.\cc:116:execute$116  = 1'b1;
    UUT.u_dut.mem[3'b000] = 8'b00000000;

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
      UUT.wr_en <= 1'b1;
    end

    // state 2
    if (cycle == 1) begin
      PI_rst_n <= 1'b1;
      UUT.rd_en <= 1'b0;
      UUT.wr_data <= 8'b00000000;
      UUT.wr_en <= 1'b1;
    end

    // state 3
    if (cycle == 2) begin
      PI_rst_n <= 1'b1;
      UUT.rd_en <= 1'b0;
      UUT.wr_data <= 8'b00000000;
      UUT.wr_en <= 1'b1;
    end

    // state 4
    if (cycle == 3) begin
      PI_rst_n <= 1'b1;
      UUT.rd_en <= 1'b0;
      UUT.wr_data <= 8'b00000000;
      UUT.wr_en <= 1'b1;
    end

    // state 5
    if (cycle == 4) begin
      PI_rst_n <= 1'b1;
      UUT.rd_en <= 1'b0;
      UUT.wr_data <= 8'b00000000;
      UUT.wr_en <= 1'b1;
    end

    // state 6
    if (cycle == 5) begin
      PI_rst_n <= 1'b1;
      UUT.rd_en <= 1'b0;
      UUT.wr_data <= 8'b00000000;
      UUT.wr_en <= 1'b1;
    end

    // state 7
    if (cycle == 6) begin
      PI_rst_n <= 1'b1;
      UUT.rd_en <= 1'b0;
      UUT.wr_data <= 8'b00000000;
      UUT.wr_en <= 1'b1;
    end

    // state 8
    if (cycle == 7) begin
      PI_rst_n <= 1'b1;
      UUT.rd_en <= 1'b0;
      UUT.wr_data <= 8'b00000000;
      UUT.wr_en <= 1'b1;
    end

    // state 9
    if (cycle == 8) begin
      PI_rst_n <= 1'b1;
      UUT.rd_en <= 1'b0;
      UUT.wr_data <= 8'b00000000;
      UUT.wr_en <= 1'b1;
    end

    // state 10
    if (cycle == 9) begin
      PI_rst_n <= 1'b1;
      UUT.rd_en <= 1'b0;
      UUT.wr_data <= 8'b00000000;
      UUT.wr_en <= 1'b0;
    end

    // state 11
    if (cycle == 10) begin
      PI_rst_n <= 1'b0;
      UUT.rd_en <= 1'b0;
      UUT.wr_data <= 8'b00000000;
      UUT.wr_en <= 1'b0;
    end

    genclock <= cycle < 11;
    cycle <= cycle + 1;
  end
endmodule
