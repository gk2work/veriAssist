`ifdef FORMAL
module formal_wrapper (
    input wire clk,
    input wire rst_n
);

    wire reset_n = rst_n;

    (* anyseq *) wire wr_en;
    (* anyseq *) wire [7:0] wr_data;
    wire full;
    (* anyseq *) wire rd_en;
    wire [7:0] rd_data;
    wire empty;

    fifo u_dut (
        .clk(clk),
        .reset_n(reset_n),
        .wr_en(wr_en),
        .wr_data(wr_data),
        .full(full),
        .rd_en(rd_en),
        .rd_data(rd_data),
        .empty(empty)
    );

    fifo_sva u_monitor (
        .clk_in(clk),
        .rst_n_in(reset_n),
        .empty(empty),
        .empty_out(empty),
        .full_out(full),
        .rd_data_out(rd_data),
        .rd_en(rd_en),
        .rd_en_in(rd_en),
        .wr_data_in(wr_data),
        .wr_en_in(wr_en)
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