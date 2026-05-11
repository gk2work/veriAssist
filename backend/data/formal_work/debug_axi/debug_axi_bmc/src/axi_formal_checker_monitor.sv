`ifdef FORMAL
module axi_formal_checker (
    input wire clk,
    input wire rst_n,
    input wire awvalid,
    input wire awready
);

    // --- assert_awready: assert property (p_awready_response) ---
    // Original SVA: awvalid && !awready |=> awvalid
    reg _va_assert_awready_triggered_1;
    always @(posedge clk) begin
        if (!rst_n) begin
            _va_assert_awready_triggered_1 <= 0;
        end else begin
            if (_va_assert_awready_triggered_1 && !(awvalid))
                assert_awready: assert(0); // FAIL: consequent not met after antecedent
            _va_assert_awready_triggered_1 <= (awvalid && !awready);
        end
    end

    // --- cover_awready: cover property (p_awready_response) ---
    // Original SVA: awvalid && !awready |=> awvalid
    reg _va_cover_awready_triggered_2;
    always @(posedge clk) begin
        if (!rst_n) begin
            _va_cover_awready_triggered_2 <= 0;
        end else begin
            if (_va_cover_awready_triggered_2 && (awvalid))
                cover_awready: cover(1);
            _va_cover_awready_triggered_2 <= (awvalid && !awready);
        end
    end

endmodule
`endif // FORMAL