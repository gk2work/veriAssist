`ifdef FORMAL
module axi_formal_checker (
    input wire clk,
    input wire rst_n,
    input wire awvalid,
    input wire awready
);

    // --- assert_must_respond: assert property (p_must_respond) ---
    // Original SVA: awvalid |=> awready
    reg _va_assert_must_respond_triggered_1;
    always @(posedge clk) begin
        if (!rst_n) begin
            _va_assert_must_respond_triggered_1 <= 0;
        end else begin
            if (_va_assert_must_respond_triggered_1 && !(awready))
                assert_must_respond: assert(0); // FAIL: consequent not met after antecedent
            _va_assert_must_respond_triggered_1 <= (awvalid);
        end
    end

endmodule
`endif // FORMAL