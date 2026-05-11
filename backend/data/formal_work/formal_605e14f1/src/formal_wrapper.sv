`ifdef FORMAL
module formal_wrapper (
    input wire clk,
    input wire rst_n
);

    (* anyseq *) wire wen;
    (* anyseq *) wire ren;
    (* anyseq *) wire [7:0] wdata;
    wire [7:0] rdata;

    fifo u_dut (
        .clk(clk),
        .rst(rst),
        .wen(wen),
        .ren(ren),
        .wdata(wdata),
        .rdata(rdata)
    );

    fifo_formal_checker u_monitor (
        .clk(clk),
        .rst_n(rst_n)
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