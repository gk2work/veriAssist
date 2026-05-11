module fifo #(
   WIDTH     = 8,   // in bit
   DEPTH     = 32,  // in words as wide as defined by WIDTH
   LOG2DEPTH = $clog2(DEPTH) // log2 of DEPTH - used for pointers
) (
   clk,
   reset_n,
   wr_en,
   wr_data,
   full,
   rd_en,
   rd_data,
   empty
);

/***********************************************************************
* Port declarations
***********************************************************************/
input  clk;
input  reset_n;
input  wr_en;
input  [WIDTH-1:0] wr_data;
output full;
input  rd_en;
output [WIDTH-1:0] rd_data;
output empty;

/***********************************************************************
* Constants
***********************************************************************/
localparam logic [LOG2DEPTH-1:0] PTR_ZERO = {LOG2DEPTH{1'b0}};
localparam logic [LOG2DEPTH-1:0] PTR_ONE  = {{LOG2DEPTH-1{1'b0}},1'b1};
localparam logic [LOG2DEPTH-1:0] PTR_X    = {LOG2DEPTH{1'bX}};
localparam logic [LOG2DEPTH-1:0] PTR_MAX  = DEPTH-1'b1;
localparam int   PTR_MSB_LOC              = LOG2DEPTH-1;

/***********************************************************************
* Signal declarations
***********************************************************************/
logic  full;
logic  empty;
logic  [WIDTH-1:0] rd_data;

logic  [DEPTH-1:0] [WIDTH-1:0] mem;
logic  [PTR_MSB_LOC:0] wr_pointer;
logic  [PTR_MSB_LOC:0] rd_pointer;
logic  [PTR_MSB_LOC:0] wr_pointer_next;
logic  [PTR_MSB_LOC:0] rd_pointer_next;

/***********************************************************************
* Write pointer register
***********************************************************************/
always@(posedge clk or negedge reset_n)
begin
   if (reset_n == 1'b0)
      begin
         wr_pointer <= PTR_ZERO;
      end
   else
      begin
         if ((wr_en == 1'b1) && (full == 1'b0 || rd_en == 1'b1))
            begin
               wr_pointer <= wr_pointer_next;
            end
         end
end

/***********************************************************************
* Next write pointer
***********************************************************************/
always@(wr_pointer)
begin
   if (wr_pointer < PTR_MAX)
      begin
         wr_pointer_next = wr_pointer + PTR_ONE;
      end
   else
      begin
         wr_pointer_next = PTR_ZERO;
      end
end

/***********************************************************************
* Write memory access
***********************************************************************/
always@(posedge clk)
begin
   if ((wr_en == 1'b1) && ((full == 1'b0) || rd_en == 1'b1))
      begin
         mem [ wr_pointer ] [WIDTH-1:0] <= wr_data;
      end
end

/***********************************************************************
* Full flag generation
***********************************************************************/
always@(posedge clk or negedge reset_n)
begin
   if (reset_n == 1'b0)
      begin
         full <= 1'b0;
      end
   else
      begin
         case ({(wr_en&(~full|rd_en)),(rd_en&~empty)})
            2'b01:
               begin
                  full <= 1'b0;
               end
            2'b10:
               if (rd_pointer == wr_pointer_next)
                  begin
                     full <= 1'b1;
                  end
               else
                  begin
                     full <= 1'b0;
                  end
            default:
                     full <= full;
         endcase
      end
end

/***********************************************************************
* Read pointer register
***********************************************************************/
always@(posedge clk or negedge reset_n)
begin
   if (reset_n == 1'b0)
      begin
         rd_pointer <= PTR_ZERO;
      end
   else
      begin
         if ((rd_en == 1'b1) && (empty == 1'b0))
            rd_pointer <= rd_pointer_next;
      end
end

/***********************************************************************
* Next read pointer
***********************************************************************/
always@(rd_pointer)
begin
   if (rd_pointer < PTR_MAX)
      rd_pointer_next = rd_pointer + PTR_ONE;
   else
      rd_pointer_next = PTR_ZERO;
end

/***********************************************************************
* Empty flag generation
***********************************************************************/
always@(posedge clk or negedge reset_n)
begin
   if (reset_n == 1'b0)
      begin
         empty <= 1'b1;
      end
   else
      begin
         case ({(wr_en&(~full|rd_en)),(rd_en&~empty)})
            2'b01:
               if (rd_pointer_next == wr_pointer)
                  begin
                     empty <= 1'b1;
                  end
               else
                  begin
                     empty <= 1'b0;
                  end
            2'b10:
               begin
                  empty <= 1'b0;
               end
            default:
               empty <= empty;
         endcase
      end
end

/***********************************************************************
* Read memory access
***********************************************************************/
always@(posedge clk or negedge reset_n)
begin
   if (reset_n == 1'b0)
      begin
         rd_data <= {WIDTH{1'b0}};
      end
   else
      begin
         if ((rd_en == 1'b1) && (empty == 1'b0))
            begin
               rd_data <= mem[rd_pointer][WIDTH-1:0];
            end
      end
end

endmodule
