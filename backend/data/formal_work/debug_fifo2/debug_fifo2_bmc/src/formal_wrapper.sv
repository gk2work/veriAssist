`ifdef FORMAL
module formal_wrapper (
    input wire clk,
    input wire rst_n
);

    (* anyseq *) wire wr_en;
    (* anyseq *) wire [7:0] wr_data;
    (* anyseq *) wire rd_en;
    wire [7:0] rd_data;
    wire full;
    wire empty;
    wire [7:0] count;

    sync_fifo u_dut (
        .clk(clk),
        .rst_n(rst_n),
        .wr_en(wr_en),
        .wr_data(wr_data),
        .rd_en(rd_en),
        .rd_data(rd_data),
        .full(full),
        .empty(empty),
        .count(count)
    );

    fifo_formal_checker u_monitor (
        .clk(clk),
        .rst_n(rst_n),
        .wr_en(wr_en),
        .full(full),
        .empty(empty),
        .rd_en(rd_en),
        .count(count)
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