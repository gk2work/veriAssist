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
  reg [7:0] PI_rd_data;
  reg [0:0] PI_rd_en;
  reg [0:0] PI_wr_en;
  reg [0:0] PI_rst_n;
  reg [0:0] PI_full;
  reg [3:0] PI_count;
  reg [7:0] PI_wr_data;
  reg [0:0] PI_empty;
  fifo_checker UUT (
    .clk(PI_clk),
    .rd_data(PI_rd_data),
    .rd_en(PI_rd_en),
    .wr_en(PI_wr_en),
    .rst_n(PI_rst_n),
    .full(PI_full),
    .count(PI_count),
    .wr_data(PI_wr_data),
    .empty(PI_empty)
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
    // UUT.$auto$async2sync.\cc:107:execute$188  = 1'b0;
    // UUT.$auto$async2sync.\cc:107:execute$194  = 1'b0;
    // UUT.$auto$async2sync.\cc:107:execute$200  = 1'b0;
    // UUT.$auto$async2sync.\cc:107:execute$206  = 1'b0;
    // UUT.$auto$async2sync.\cc:107:execute$212  = 1'b0;
    // UUT.$auto$async2sync.\cc:107:execute$218  = 1'b0;
    // UUT.$auto$async2sync.\cc:107:execute$224  = 1'b0;
    // UUT.$auto$async2sync.\cc:107:execute$230  = 1'b0;
    // UUT.$auto$async2sync.\cc:116:execute$180  = 1'b1;
    // UUT.$auto$async2sync.\cc:116:execute$186  = 1'b1;
    // UUT.$auto$async2sync.\cc:116:execute$222  = 1'b1;
    // UUT.$auto$async2sync.\cc:116:execute$228  = 1'b1;
    UUT._va_assert_count_stable_triggered_3 = 1'b0;
    UUT._va_assert_read_dec_triggered_2 = 1'b0;
    UUT._va_assert_write_inc_triggered_1 = 1'b1;
    UUT.count_past1 = 4'b0000;
    UUT.count_prev = 4'b0000;
    UUT.empty_prev = 1'b0;
    UUT.full_prev = 1'b0;
    UUT.rd_en_past1 = 1'b0;
    UUT.wr_en_past1 = 1'b0;

    // state 0
    PI_rd_data = 8'b00000000;
    PI_rd_en = 1'b0;
    PI_wr_en = 1'b0;
    PI_rst_n = 1'b1;
    PI_full = 1'b0;
    PI_count = 4'b0100;
    PI_wr_data = 8'b00000000;
    PI_empty = 1'b0;
  end
  always @(posedge clock) begin
    // state 1
    if (cycle == 0) begin
      PI_rd_data <= 8'b00000000;
      PI_rd_en <= 1'b0;
      PI_wr_en <= 1'b0;
      PI_rst_n <= 1'b0;
      PI_full <= 1'b0;
      PI_count <= 4'b0000;
      PI_wr_data <= 8'b00000000;
      PI_empty <= 1'b0;
    end

    genclock <= cycle < 1;
    cycle <= cycle + 1;
  end
endmodule
