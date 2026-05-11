`ifdef FORMAL
module mini_checker (
    input wire clk,
    input wire rst_n,
    input wire a,
    input wire b
);

    // --- assert_p1: assert property (p1) ---
    // Original SVA: a |-> b
    always @(posedge clk) begin
        if (!(!rst_n)) begin
            if (a && !(b))
                begin end // disabled assertion assert_p1
        end
    end

    // --- assert_p2: assert property (p2) ---
    // Original SVA: !a |-> !b
    always @(posedge clk) begin
        if (!(!rst_n)) begin
            if (!a && !(!b))
                assert_p2: assert(0);
        end
    end

endmodule
`endif // FORMAL