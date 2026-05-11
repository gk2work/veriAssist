`ifdef FORMAL
module fsm_formal_checker (
    input wire clk,
    input wire rst_n,
    input wire [2:0] state
);

    // --- assert_legal_state: assert property (p_no_illegal_state) ---
    // Original SVA: (state <= 4)
    always @(posedge clk) begin
        if (!(!rst_n)) begin
            assert_legal_state: assert((state <= 4));
        end
    end

    // --- cover_legal_state: cover property (p_no_illegal_state) ---
    // Original SVA: (state <= 4)
    always @(posedge clk) begin
        if (!(!rst_n)) begin
            if ((state <= 4)) cover_legal_state: cover(1);
        end
    end

endmodule
`endif // FORMAL