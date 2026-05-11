`ifdef FORMAL
module fifo_formal_checker (
    input wire clk,
    input wire rst_n
);

    // Past-value registers for edge/stability detection
    reg wr_data_prev;

    always @(posedge clk) begin
        if (!rst_n) begin
            wr_data_prev <= 0;
        end else begin
            wr_data_prev <= wr_data;
        end
    end

    // --- cover_fifo_underfill: cover property (p_fifo_underfill) ---
    // Original SVA: wr_en && !full |-> ##1 rd_en[->1] ##0 (rd_data == $stable(wr_data))
    reg [0:0] _va_cover_fifo_underfill_delay_1;
    always @(posedge clk) begin
        if (!rst_n) begin
            _va_cover_fifo_underfill_delay_1 <= 0;
        end else begin
            _va_cover_fifo_underfill_delay_1 <= {_va_cover_fifo_underfill_delay_1[-1:0], (wr_en && !full)};
            if (_va_cover_fifo_underfill_delay_1[0] && (rd_en[->1] (rd_data == (wr_data == wr_data_prev))))
                cover_fifo_underfill: cover(1);
        end
    end

endmodule
`endif // FORMAL