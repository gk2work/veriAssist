`ifdef FORMAL
module fifo_formal_checker (
    input wire clk,
    input wire rst_n,
    input wire wr_en,
    input wire full,
    input wire empty,
    input wire rd_en,
    input wire [3:0] count
);

    // --- assert_count_bounded: assert property (p_count_bounded) ---
    // Original SVA: (count <= 8)
    always @(posedge clk) begin
        if (!(!rst_n)) begin
            assert_count_bounded: assert((count <= 8));
        end
    end

    // --- cover_count_bounded: cover property (p_count_bounded) ---
    // Original SVA: (count <= 8)
    always @(posedge clk) begin
        if (!(!rst_n)) begin
            if ((count <= 8)) cover_count_bounded: cover(1);
        end
    end

endmodule
`endif // FORMAL