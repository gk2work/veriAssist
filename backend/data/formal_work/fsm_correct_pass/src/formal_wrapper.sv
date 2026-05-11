`ifdef FORMAL
module formal_wrapper (
    input wire clk,
    input wire rst_n
);

    (* anyseq *) wire start;
    (* anyseq *) wire data_valid;
    (* anyseq *) wire resp_ok;
    wire [2:0] state;

    protocol_fsm u_dut (
        .clk(clk),
        .rst_n(rst_n),
        .start(start),
        .data_valid(data_valid),
        .resp_ok(resp_ok),
        .state(state)
    );

    fsm_formal_checker u_monitor (
        .clk(clk),
        .rst_n(rst_n),
        .state(state)
    );

    // Assume reset is active for at least the first cycle
    reg _va_past_valid;
    always @(posedge clk) begin
        if (!_va_past_valid)
            _va_past_valid <= 1;
    end
    initial _va_past_valid = 0;
    always @(*) begin
        if (!_va_past_valid)
            assume(!rst_n);
    end

endmodule
`endif