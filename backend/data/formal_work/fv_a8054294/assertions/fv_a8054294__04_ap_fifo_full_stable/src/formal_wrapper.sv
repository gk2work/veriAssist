`ifdef FORMAL
module formal_wrapper (
    input wire clk,
    input wire rst_n
);

    wire reset_n = rst_n;

    (* anyseq *) wire wr_en;
    (* anyseq *) wire rd_en;
    (* anyseq *) wire [7:0] wr_data;
    wire [7:0] rd_data;
    wire full;
    wire empty;

    fifo u_dut (
        .clk(clk),
        .reset_n(reset_n),
        .wr_en(wr_en),
        .rd_en(rd_en),
        .wr_data(wr_data),
        .rd_data(rd_data),
        .full(full),
        .empty(empty)
    );

    fifo_sva u_monitor (
        .clk(clk),
        .reset_n(reset_n),
        .wr_en(wr_en),
        .rd_en(rd_en),
        .full(full),
        .empty(empty)
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
            assume(!reset_n);
    end

endmodule
`endif