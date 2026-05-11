`ifdef FORMAL
module fsm_formal_checker (
    input wire clk,
    input wire rst_n,
    input wire [2:0] state,
    input wire start,
    input wire data_valid,
    input wire resp_ok,
    input wire error
);

    // --- assert_resp_done: assert property (p_resp_to_done) ---
    // Original SVA: (state == 3) && resp_ok && !error |=> (state == 4)
    reg _va_assert_resp_done_triggered_1;
    always @(posedge clk) begin
        if (!rst_n) begin
            _va_assert_resp_done_triggered_1 <= 0;
        end else begin
            if (_va_assert_resp_done_triggered_1 && !((state == 4)))
                assert_resp_done: assert(0); // FAIL: consequent not met after antecedent
            _va_assert_resp_done_triggered_1 <= ((state == 3) && resp_ok && !error);
        end
    end

    // --- assert_idle_addr: assert property (p_idle_to_addr) ---
    // Original SVA: (state == 0) && start |=> (state == 1)
    reg _va_assert_idle_addr_triggered_2;
    always @(posedge clk) begin
        if (!rst_n) begin
            _va_assert_idle_addr_triggered_2 <= 0;
        end else begin
            if (_va_assert_idle_addr_triggered_2 && !((state == 1)))
                assert_idle_addr: assert(0); // FAIL: consequent not met after antecedent
            _va_assert_idle_addr_triggered_2 <= ((state == 0) && start);
        end
    end

endmodule
`endif // FORMAL