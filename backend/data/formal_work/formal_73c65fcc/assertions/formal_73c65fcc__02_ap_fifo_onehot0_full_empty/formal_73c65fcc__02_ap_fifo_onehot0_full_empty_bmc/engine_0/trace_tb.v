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
  reg [0:0] PI_empty_out;
  reg [0:0] PI_wr_en_in;
  reg [0:0] PI_clk_in;
  reg [0:0] PI_wr_data_in;
  reg [0:0] PI_rd_data_out;
  reg [0:0] PI_full_out;
  reg [0:0] PI_rd_en_in;
  reg [0:0] PI_rst_n_in;
  reg [0:0] PI_data_start;
  fifo UUT (
    .empty_out(PI_empty_out),
    .wr_en_in(PI_wr_en_in),
    .clk_in(PI_clk_in),
    .wr_data_in(PI_wr_data_in),
    .rd_data_out(PI_rd_data_out),
    .full_out(PI_full_out),
    .rd_en_in(PI_rd_en_in),
    .rst_n_in(PI_rst_n_in),
    .data_start(PI_data_start)
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
    // UUT.$auto$async2sync.\cc:107:execute$165  = 1'b0;
    // UUT.$auto$async2sync.\cc:116:execute$169  = 1'b1;

    // state 0
    PI_empty_out = 1'b1;
    PI_wr_en_in = 1'b0;
    PI_clk_in = 1'b0;
    PI_wr_data_in = 1'b0;
    PI_rd_data_out = 1'b0;
    PI_full_out = 1'b1;
    PI_rd_en_in = 1'b0;
    PI_rst_n_in = 1'b1;
    PI_data_start = 1'b0;
  end
  always @(posedge clock) begin
    // state 1
    if (cycle == 0) begin
      PI_empty_out <= 1'b0;
      PI_wr_en_in <= 1'b0;
      PI_clk_in <= 1'b0;
      PI_wr_data_in <= 1'b0;
      PI_rd_data_out <= 1'b0;
      PI_full_out <= 1'b0;
      PI_rd_en_in <= 1'b0;
      PI_rst_n_in <= 1'b0;
      PI_data_start <= 1'b0;
    end

    genclock <= cycle < 1;
    cycle <= cycle + 1;
  end
endmodule
