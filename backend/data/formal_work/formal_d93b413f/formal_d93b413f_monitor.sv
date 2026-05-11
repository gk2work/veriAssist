`ifdef FORMAL
module chk (
    input wire clk,
    input wire rst_n,
    input wire a,
    input wire b
);

    // --- assert_p1: assert property (p1) ---
    // Original SVA: a |=> b
    reg _va_assert_p1_triggered_1;
    always @(posedge clk) begin
        if (!rst_n) begin
            _va_assert_p1_triggered_1 <= 0;
        end else begin
            if (_va_assert_p1_triggered_1 && !(b))
                assert_p1: assert(0); // FAIL: consequent not met after antecedent
            _va_assert_p1_triggered_1 <= (a);
        end
    end

endmodule
`endif // FORMAL