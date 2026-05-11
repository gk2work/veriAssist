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
input  clk;                      // Synchronous FIFO clock
input  reset_n;                  // Asynchronous reset - it is assumed
                                 // that the signal's de-assertion is 
                                 // properly aligned with the clock
                                 // before arriving at this module
input  wr_en;                    // Write enable - when ever this signal
                                 // is high a new word is written to the
                                 // FIFO - unless the FIFO is full, then
                                 // wr_en may not be asserted by the 
                                 // surrounding system.
input  [WIDTH-1:0] wr_data;      // Write data
output full;                     // FIFO full flag - when asserted no
                                 // writes are allowed.
input  rd_en;                    // read enable, when ever this signal
                                 // is asserted new read data will be
                                 // made available in the next clock
                                 // cycle. When the FIFO is empty the
                                 // output register will not be updated.
                                 // In general the surrounding system
                                 // must monitor the empty signal to
                                 // ensure it is reading valid data.
output [WIDTH-1:0] rd_data;      // Read data - registerd
output empty;                    // FIFO empty flag


/***********************************************************************
* Constants
***********************************************************************/
localparam logic [LOG2DEPTH-1:0] PTR_ZERO = {LOG2DEPTH{1'b0}};
localparam logic [LOG2DEPTH-1:0] PTR_ONE  = {{LOG2DEPTH-1{1'b0}},1'b1};
localparam logic [LOG2DEPTH-1:0] PTR_X    = {LOG2DEPTH{1'bX}};
localparam logic [LOG2DEPTH-1:0] PTR_MAX  = DEPTH-1'b1; 
// Index of most significant bit
localparam int   PTR_MSB_LOC              = LOG2DEPTH-1;    

/***********************************************************************
* Signal declarations
***********************************************************************/
logic  full;
logic  empty;
logic  [WIDTH-1:0] rd_data;

logic  [DEPTH-1:0] [WIDTH-1:0] mem;      // FIFO memory
logic  [PTR_MSB_LOC:0] wr_pointer;       // Write pointer
logic  [PTR_MSB_LOC:0] rd_pointer;       // Read pointer
logic  [PTR_MSB_LOC:0] wr_pointer_next;  // Next write pointer
logic  [PTR_MSB_LOC:0] rd_pointer_next;  // Next read pointer

/***********************************************************************
* Write pointer register
*
* As the depth of the FIFO is not fixed to a power of two the wrapping
* back to zero is implemented explicitly.
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
*
* The FIFO is full when the pointer are the same and the last access
* was a write only.
* The issue at hand is that it is good coding practice to register all
* outputs of a module, thus full as well. When registering the full
* signal the information of the pointers is one cycle too late:
* At clock 1 write fills the FIFO, though as the pointers are not 
* fulfilling the above definition the full flag register is not set
* to one. This only happens at clock 2, as now the definition is 
* fulfilled.
* If the full flag is to be registered one needs to look ahead and 
* cover all possible changes for the next clock event:
* 
* 1. Neither read or write pointer moves, no update and the above 
*    definition is used.
* 2. Only read pointer moves, compare wr_pointer with rd_pointer_next.
*    Though actually the comparison is not even necessary, if it is only
*    read from the FIFO, then in the next cycle the FIFO can NOT be 
*    full!
* 3. Only write pointer moves, compare wr_pointer_next with rd_pointer.
* 4. Both pointers move, as both increment they will not move relative
*    to each other, therefore full will stay asserted if it already
*    had been asserted. If not it is de-asserted.
*
* Last but not least the wr_en should be qualified with the full flag 
* and the rd_en with the empty flag to avoid full flag changes when
* illegal writes or reads are seen
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
               // Only the read pointer moves, therefore the
               // FIFO will never be full afterwards.
               begin
                  full <= 1'b0;
               end
            2'b10: 
               // It is only written to the FIFO - compare
               // current read_pointer with wr_pointer_next
               if (rd_pointer == wr_pointer_next)
                  begin
                     full <= 1'b1;
                  end
               else
                  begin
                     full <= 1'b0;
                  end
            default: 
               // Covers 2'b00 & 2'11 as well
               // In this case neither pointer moves or both at the 
               // same time. In this case the flag doesn change
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
*
* The FIFO is empty when the pointer are the same and the last access
* was a read.
* The issue at hand is that it is good coding practice to register all
* outputs of a module, thus empty as well. When registering the empty
* signal the information of the pointers is one cycle too late:
* At clock 1 read empties the FIFO, though as the pointers are not 
* fulfilling the above definition, the empty flag register is not set
* to one. This only happens at clock 2, as now the definition is 
* fulfilled.
* If the empty flag is to be registered one needs to look ahead and 
* cover all possible changes for the next clock event:
* 
* 1. Neither read or write pointer moves, no update and the above 
*    definition is used.
* 2. Only write pointer moves, compare wr_pointer_next with rd_pointer.
*    Though actually the comparison is not even necessary, if it is only
*    written to the FIFO then in the next cycle the FIFO can NOT be 
*    empty!
* 3. Only read pointer moves, compare wr_pointer with rd_pointer_next.
* 4. Both pointers move, as both increment they will not move relative
*    to each other, therefore empty will stay the same value as in the
*    cycle before.
*
* Last but not least the wr_en should be qualified with the full flag 
* and the rd_en with the empty flag to avoid empty flag changes when
* illegal writes or reads are seen
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
               // It is only read from the FIFO - compare
               // current wr_pointer with rd_pointer_next
               if (rd_pointer_next == wr_pointer)
                  begin
                     empty <= 1'b1;
                  end
               else
                  begin
                     empty <= 1'b0;
                  end
            2'b10: 
               // Only the write pointer moves, therefore the
               // FIFO will never be empty afterwards.
               begin
                  empty <= 1'b0;
               end
            default: 
               // Covers 2'b00 & 2'11 as well
               // In this case neither pointer moves or both at the
               // same time. In this case the flag doesn't change.
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
               rd_data    <=    mem            [rd_pointer] [WIDTH-1:0];
            end
      end
end

endmodule



module fifo_sva ();

//------------------------------------------ Macros -------------------------------------------

  `define clk_in       fifo.clk
  `define rst_n_in     fifo.reset_n
  `define wr_en_in     fifo.wr_en
  `define wr_data_in   fifo.wr_data
  `define rd_en_in     fifo.rd_en
  `define rd_data_out  fifo.rd_data
  `define full_out     fifo.full
  `define empty_out    fifo.empty

//---------------------------------------- Properties -----------------------------------------

  //===========================================================================================
  // FIFO is full
  //===========================================================================================
  property fifo_full;
    (1
  |->
    (`full_out) );
  endproperty: fifo_full

  //===========================================================================================
  // FIFO is empty
  //===========================================================================================
  property fifo_empty;
    (1
  |->
    (`empty_out) );
  endproperty: fifo_empty

  //===========================================================================================
  // FIFO is not both full and empty
  //===========================================================================================
  property fifo_not_full_empty;
    (1
  |->
    ($onehot0({`full_out,`empty_out})) );
  endproperty: fifo_not_full_empty

  //===========================================================================================
  // If the FIFO is full, no data is written to the FIFO
  //===========================================================================================
  property fifo_full_no_write;
    ( (`full_out)
  |->
    (!`wr_en_in) );
  endproperty: fifo_full_no_write

  //===========================================================================================
  // If the FIFO is empty, no data is read from the FIFO
  //===========================================================================================
  property fifo_empty_no_read;
    ( (`empty_out)
  |->
    (!`rd_en_in) );
  endproperty: fifo_empty_no_read

  //===========================================================================================
  // There is a falling edge on the full output
  //===========================================================================================
  property fifo_full_falling_edge;
    (1
  |->
    ($fell(`full_out)) );
  endproperty: fifo_full_falling_edge

  //===========================================================================================
  // The concatenation of full and empty ({full,empty}) is zero onehot
  //===========================================================================================
  property fifo_onehot0_full_empty;
    (1
  |->
    ($onehot0({`full_out, `empty_out})) );
  endproperty: fifo_onehot0_full_empty

  //===========================================================================================
  // If the FIFO just became full (a rising edge of the full signal), then there was a write in
  // the previous cycle
  //===========================================================================================
  property fifo_full_prev_write;
    ( ($rose(`full_out))
  |->
    ($past(`wr_en_in)) );
  endproperty: fifo_full_prev_write

  //===========================================================================================
  // If the FIFO just became empty, then there was a read, but no write in the previous cycle
  //===========================================================================================
  property fifo_empty_prev_read_no_write;
    ( ($rose(`empty_out))
  |->
    ( ($past(`rd_en_in)) &&
    (!$past(`wr_en_in)) ));
  endproperty: fifo_empty_prev_read_no_write

  //===========================================================================================
  // If there is a write, the FIFO is not empty in the next cycle
  //===========================================================================================
  property fifo_write_not_empty;
    ( (`wr_en_in)
  |->
    ( ##1 !`empty_out) );
  endproperty: fifo_write_not_empty

  //===========================================================================================
  // In the cycle after reset, the FIFO is empty
  //===========================================================================================
  property fifo_empty_after_reset;
    ( ($rose(`rst_n_in))
  |->
    (`empty_out) );
  endproperty: fifo_empty_after_reset

  //===========================================================================================
  // If the read and write enable of the FIFO are equal, the full and empty outputs stay stable
  //===========================================================================================
  property fifo_read_write_equal;
    ( (`rd_en_in == `wr_en_in)
  |->
    ( ##1 $stable(`full_out) &&
    ($stable(`empty_out))) );
  endproperty: fifo_read_write_equal

  //===========================================================================================
  // If there is a write, but no read for 32 consecutive cycles, the FIFO is full in the next
  // cycle
  //===========================================================================================
  property fifo_write_32_full;
    ( ((`wr_en_in && !`rd_en_in) [*32])
  |->
    ( ##1 `full_out) );
  endproperty: fifo_write_32_full

  //===========================================================================================
  // 28 cycles after the FIFO is empty, it is full
  //===========================================================================================
  property fifo_full_after_28;
    ( (`empty_out)
  |->
    ( ##28 `full_out) );
  endproperty: fifo_full_after_28

  //===========================================================================================
  // If the FIFO is empty and data is written, and in the next cycle, data is read, then the
  // read data in the following cycle is the data written to the FIFO two cycles ago
  //===========================================================================================
  property fifo_data_after_empty;
    ( ((`empty_out) &&
    (`wr_en_in) ##1
    (`rd_en_in))
  |->
    ( ##1 (`rd_data_out == $past(`wr_data_in, 2))) );
  endproperty: fifo_data_after_empty

  //===========================================================================================
  // If the FIFO is empty and data is written, and in the next 1 to 4 cycles, no data is read,
  // and in the next cycle, data is read, then the read data in the following cycle is the data
  // written to the FIFO in the beginning
  //===========================================================================================
  property fifo_data_after_empty_1_4;
    reg[7:0] data_start;
    ( (((`empty_out && `wr_en_in), data_start = `wr_data_in) ##1
    (!`rd_en_in) [*1:4] ##1
    (`rd_en_in))
  |->
    ( ##1 (`rd_data_out == data_start)) );
  endproperty: fifo_data_after_empty_1_4
//---------------------------------------------------------------------------------------------

//-------------------------------------- Covers/Witness ---------------------------------------

  wp_fifo_full              : cover property(@(posedge `clk_in) disable iff (!`rst_n_in) fifo_full);
  wp_fifo_empty             : cover property(@(posedge `clk_in) disable iff (!`rst_n_in) fifo_empty);
  wp_fifo_full_falling_edge : cover property(@(posedge `clk_in) disable iff (!`rst_n_in) fifo_full_falling_edge);
  wp_fifo_full_after_28     : cover property(@(posedge `clk_in) disable iff (!`rst_n_in) fifo_full_after_28);
//---------------------------------------------------------------------------------------------

//---------------------------------------- Assertions -----------------------------------------

  ap_fifo_not_full_empty           : assert property(@(posedge `clk_in) disable iff (!`rst_n_in) fifo_not_full_empty);
  ap_fifo_onehot0_full_empty       : assert property(@(posedge `clk_in) disable iff (!`rst_n_in) fifo_onehot0_full_empty);
  ap_fifo_full_prev_write          : assert property(@(posedge `clk_in) disable iff (!`rst_n_in) fifo_full_prev_write);
  ap_fifo_empty_prev_read_no_write : assert property(@(posedge `clk_in) disable iff (!`rst_n_in) fifo_empty_prev_read_no_write);
  ap_fifo_write_not_empty          : assert property(@(posedge `clk_in) disable iff (!`rst_n_in) fifo_write_not_empty);
  ap_fifo_empty_after_reset        : assert property(@(posedge `clk_in) disable iff (!`rst_n_in) fifo_empty_after_reset);
  ap_fifo_read_write_equal         : assert property(@(posedge `clk_in) disable iff (!`rst_n_in) fifo_read_write_equal);
  ap_fifo_write_32_full            : assert property(@(posedge `clk_in) disable iff (!`rst_n_in) fifo_write_32_full);
  ap_fifo_data_after_empty         : assert property(@(posedge `clk_in) disable iff (!`rst_n_in) fifo_data_after_empty);
  ap_fifo_data_after_empty_1_4     : assert property(@(posedge `clk_in) disable iff (!`rst_n_in) fifo_data_after_empty_1_4);
//---------------------------------------------------------------------------------------------

//--------------------------------------- Constraints -----------------------------------------

  cp_fifo_full_no_write : assume property(@(posedge `clk_in) disable iff (!`rst_n_in) fifo_full_no_write);
  cp_fifo_empty_no_read : assume property(@(posedge `clk_in) disable iff (!`rst_n_in) fifo_empty_no_read);
//---------------------------------------------------------------------------------------------

endmodule: fifo_sva

bind fifo fifo_sva inst_fifo_sva(.*);