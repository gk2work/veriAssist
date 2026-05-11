`ifdef FORMAL
module formal_wrapper (
    input wire clk,
    input wire rst_n
);

    (* anyseq *) wire awvalid;
    wire awready;

    axi_slave u_dut (
        .clk(clk),
        .rst_n(rst_n),
        .awvalid(awvalid),
        .awready(awready)
    );

    axi_formal_checker u_monitor (
        .clk(clk),
        .rst_n(rst_n),
        .awvalid(awvalid),
        .awready(awready)
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