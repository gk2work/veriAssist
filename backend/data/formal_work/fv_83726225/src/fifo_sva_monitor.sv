`ifdef FORMAL
module fifo_sva (
    input wire clk,
    input wire reset_n,
    input wire wr_en,
    input wire rd_en,
    input wire full,
    input wire empty
);

    // WARNING: property 'empty' not found for wp_fifo_empty
    // WARNING: property 'full' not found for wp_fifo_full
endmodule
`endif // FORMAL