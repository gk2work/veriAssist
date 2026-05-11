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
  reg [7:0] PI_rd_data;
  wire [0:0] PI_clk = clock;
  reg [3:0] PI_count;
  reg [7:0] PI_wr_data;
  reg [0:0] PI_empty;
  reg [0:0] PI_wr_en;
  reg [0:0] PI_full;
  reg [0:0] PI_rd_en;
  reg [0:0] PI_rst_n;
  fifo_checker UUT (
    .rd_data(PI_rd_data),
    .clk(PI_clk),
    .count(PI_count),
    .wr_data(PI_wr_data),
    .empty(PI_empty),
    .wr_en(PI_wr_en),
    .full(PI_full),
    .rd_en(PI_rd_en),
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
    // UUT.$auto$async2sync.\cc:107:execute$127  = 1'b0;
    // UUT.$auto$async2sync.\cc:116:execute$131  = 1'b1;
    UUT._va_assert_count_stable_triggered_3 = 1'b1;
    UUT.count_prev = 4'b1000;

    // state 0
    PI_rd_data = 8'b00000000;
    PI_count = 4'b0000;
    PI_wr_data = 8'b00000000;
    PI_empty = 1'b0;
    PI_wr_en = 1'b0;
    PI_full = 1'b0;
    PI_rd_en = 1'b0;
    PI_rst_n = 1'b1;
  end
  always @(posedge clock) begin
    // state 1
    if (cycle == 0) begin
      PI_rd_data <= 8'b00000000;
      PI_count <= 4'b0000;
      PI_wr_data <= 8'b00000000;
      PI_empty <= 1'b0;
      PI_wr_en <= 1'b0;
      PI_full <= 1'b0;
      PI_rd_en <= 1'b0;
      PI_rst_n <= 1'b0;
    end

    genclock <= cycle < 1;
    cycle <= cycle + 1;
  end
endmodule
