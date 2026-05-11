module fifo #(
   parameter WIDTH     = 8,
   parameter DEPTH     = 32,
   parameter LOG2DEPTH = $clog2(DEPTH)
) (
   input  clk,
   input  reset_n,
   input  wr_en,
   input  [WIDTH-1:0] wr_data,
   output logic full,
   input  rd_en,
   output logic [WIDTH-1:0] rd_data,
   output logic empty
);

localparam logic [LOG2DEPTH-1:0] PTR_ZERO = {LOG2DEPTH{1'b0}};
localparam logic [LOG2DEPTH-1:0] PTR_ONE  = {{LOG2DEPTH-1{1'b0}},1'b1};
localparam logic [LOG2DEPTH-1:0] PTR_MAX  = DEPTH-1'b1;

logic [DEPTH-1:0][WIDTH-1:0] mem;
logic [LOG2DEPTH-1:0] wr_pointer, rd_pointer;
logic [LOG2DEPTH-1:0] wr_pointer_next, rd_pointer_next;

// Write pointer
always @(posedge clk or negedge reset_n) begin
   if (!reset_n)
      wr_pointer <= PTR_ZERO;
   else if (wr_en && (!full || rd_en))
      wr_pointer <= wr_pointer_next;
end

// Next write pointer
always @(*) begin
   if (wr_pointer < PTR_MAX)
      wr_pointer_next = wr_pointer + PTR_ONE;
   else
      wr_pointer_next = PTR_ZERO;
end

// Memory write
always @(posedge clk) begin
   if (wr_en && (!full || rd_en))
      mem[wr_pointer] <= wr_data;
end

// Full logic
always @(posedge clk or negedge reset_n) begin
   if (!reset_n)
      full <= 1'b0;
   else begin
      case ({(wr_en & (~full | rd_en)), (rd_en & ~empty)})
         2'b01: full <= 1'b0;
         2'b10: full <= (rd_pointer == wr_pointer_next);
         default: full <= full;
      endcase
   end
end

// Read pointer
always @(posedge clk or negedge reset_n) begin
   if (!reset_n)
      rd_pointer <= PTR_ZERO;
   else if (rd_en && !empty)
      rd_pointer <= rd_pointer_next;
end

// Next read pointer
always @(*) begin
   if (rd_pointer < PTR_MAX)
      rd_pointer_next = rd_pointer + PTR_ONE;
   else
      rd_pointer_next = PTR_ZERO;
end

// Empty logic
always @(posedge clk or negedge reset_n) begin
   if (!reset_n)
      empty <= 1'b1;
   else begin
      case ({(wr_en & (~full | rd_en)), (rd_en & ~empty)})
         2'b01: empty <= (rd_pointer_next == wr_pointer);
         2'b10: empty <= 1'b0;
         default: empty <= empty;
      endcase
   end
end

// Read data
always @(posedge clk or negedge reset_n) begin
   if (!reset_n)
      rd_data <= '0;
   else if (rd_en && !empty)
      rd_data <= mem[rd_pointer];
end

endmodule