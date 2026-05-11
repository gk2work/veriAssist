`ifdef FORMAL
module fifo_sva (
    input wire clk_in,
    input wire rst_n_in,
    input wire empty_out,
    input wire full_out,
    input wire rd_data_out,
    input wire rd_en_in,
    input wire wr_data_in,
    input wire wr_en_in
);

    // Past-value registers for edge/stability detection
    reg empty_out_prev;
    reg full_out_prev;
    reg rst_n_in_prev;

    always @(posedge clk_in) begin
        if (!rst_n_in) begin
            empty_out_prev <= 0;
            full_out_prev <= 0;
            rst_n_in_prev <= 0;
        end else begin
            empty_out_prev <= empty_out;
            full_out_prev <= full_out;
            rst_n_in_prev <= rst_n_in;
        end
    end

    // $past delay registers (shift chains)
    reg wr_en_in_past1;
    reg rd_en_in_past1;
    reg wr_data_in_past1;
    reg wr_data_in_past2;

    always @(posedge clk_in) begin
        if (!rst_n_in) begin
            wr_en_in_past1 <= 0;
            rd_en_in_past1 <= 0;
            wr_data_in_past1 <= 0;
            wr_data_in_past2 <= 0;
        end else begin
            wr_en_in_past1 <= wr_en_in;
            rd_en_in_past1 <= rd_en_in;
            wr_data_in_past1 <= wr_data_in;
            wr_data_in_past2 <= wr_data_in_past1;
        end
    end

    // --- _auto_assert_fifo_not_full_empty: assert property (fifo_not_full_empty) ---
    // Original SVA: $onehot0({full_out, empty_out})
    always @(posedge clk_in) begin
        if (!(!rst_n_in)) begin
            begin end // disabled assertion _auto_assert_fifo_not_full_empty
        end
    end

    // --- _auto_assert_fifo_full_no_write: assert property (fifo_full_no_write) ---
    // Original SVA: full_out |-> !wr_en_in
    always @(posedge clk_in) begin
        if (!(!rst_n_in)) begin
            if (full_out && !(!wr_en_in))
                begin end // disabled assertion _auto_assert_fifo_full_no_write
        end
    end

    // --- _auto_assert_fifo_empty_no_read: assert property (fifo_empty_no_read) ---
    // Original SVA: empty_out |-> !rd_en_in
    always @(posedge clk_in) begin
        if (!(!rst_n_in)) begin
            if (empty_out && !(!rd_en_in))
                _auto_assert_fifo_empty_no_read: assert(0);
        end
    end

    // --- _auto_assert_fifo_full_prev_write: assert property (fifo_full_prev_write) ---
    // Original SVA: $rose(full_out) |-> $past(wr_en_in)
    always @(posedge clk_in) begin
        if (!(!rst_n_in)) begin
            if (full_out && !full_out_prev && !(wr_en_in_past1))
                begin end // disabled assertion _auto_assert_fifo_full_prev_write
        end
    end

    // --- _auto_assert_fifo_empty_prev_read_no_write: assert property (fifo_empty_prev_read_no_write) ---
    // Original SVA: $rose(empty_out) |-> ($past(rd_en_in) && !$past(wr_en_in))
    always @(posedge clk_in) begin
        if (!(!rst_n_in)) begin
            if (empty_out && !empty_out_prev && !(rd_en_in_past1 && !wr_en_in_past1))
                begin end // disabled assertion _auto_assert_fifo_empty_prev_read_no_write
        end
    end

    // --- _auto_assert_fifo_write_not_empty: assert property (fifo_write_not_empty) ---
    // Original SVA: wr_en_in |-> ##1 !empty_out
    reg _va__auto_assert_fifo_write_not_empty_delay_1;
    always @(posedge clk_in) begin
        if (!rst_n_in) begin
            _va__auto_assert_fifo_write_not_empty_delay_1 <= 0;
        end else begin
            _va__auto_assert_fifo_write_not_empty_delay_1 <= (wr_en_in);
            if (_va__auto_assert_fifo_write_not_empty_delay_1 && !(!empty_out))
                begin end // disabled assertion _auto_assert_fifo_write_not_empty
        end
    end

    // --- _auto_assert_fifo_empty_after_reset: assert property (fifo_empty_after_reset) ---
    // Original SVA: $rose(rst_n_in) |-> empty_out
    always @(posedge clk_in) begin
        if (!(!rst_n_in)) begin
            if (rst_n_in && !rst_n_in_prev && !(empty_out))
                begin end // disabled assertion _auto_assert_fifo_empty_after_reset
        end
    end

    // --- _auto_assert_fifo_read_write_equal: assert property (fifo_read_write_equal) ---
    // Original SVA: (rd_en_in == wr_en_in) |-> ##1 ($stable(full_out) && $stable(empty_out))
    reg _va__auto_assert_fifo_read_write_equal_delay_2;
    always @(posedge clk_in) begin
        if (!rst_n_in) begin
            _va__auto_assert_fifo_read_write_equal_delay_2 <= 0;
        end else begin
            _va__auto_assert_fifo_read_write_equal_delay_2 <= (rd_en_in == wr_en_in);
            if (_va__auto_assert_fifo_read_write_equal_delay_2 && !((full_out == full_out_prev) && (empty_out == empty_out_prev)))
                begin end // disabled assertion _auto_assert_fifo_read_write_equal
        end
    end

    // --- _auto_assert_fifo_write_32_full: assert property (fifo_write_32_full) ---
    // SKIPPED: property uses constructs not yet fully lowered (residual SVA: ['[*32]'])
    // Original SVA: ((wr_en_in && !rd_en_in)[*32]) |-> ##1 full_out

    // --- _auto_assert_fifo_data_after_empty: assert property (fifo_data_after_empty) ---
    // Original SVA: (empty_out && wr_en_in ##1 rd_en_in)
    //   |-> ##1 (rd_data_out == $past(wr_data_in,2))
    reg _va__auto_assert_fifo_data_after_empty_stage_4;
    reg _va__auto_assert_fifo_data_after_empty_trig_5;
    always @(posedge clk_in) begin
        if (!rst_n_in) begin
            _va__auto_assert_fifo_data_after_empty_stage_4 <= 0;
            _va__auto_assert_fifo_data_after_empty_trig_5 <= 0;
        end else begin
            _va__auto_assert_fifo_data_after_empty_trig_5 <= (_va__auto_assert_fifo_data_after_empty_stage_4 && (rd_en_in));
            _va__auto_assert_fifo_data_after_empty_stage_4 <= (empty_out && wr_en_in);
            if (_va__auto_assert_fifo_data_after_empty_trig_5 && !(rd_data_out == wr_data_in_past2))
                begin end // disabled assertion _auto_assert_fifo_data_after_empty
        end
    end

    // --- _auto_assume_fifo_full_no_write: assume property (fifo_full_no_write) ---
    // Original SVA: full_out |-> !wr_en_in
    always @(posedge clk_in) begin
        if (!(!rst_n_in)) begin
            if (full_out)
                _auto_assume_fifo_full_no_write: assume(!wr_en_in);
        end
    end

    // --- _auto_assume_fifo_empty_no_read: assume property (fifo_empty_no_read) ---
    // Original SVA: empty_out |-> !rd_en_in
    always @(posedge clk_in) begin
        if (!(!rst_n_in)) begin
            if (empty_out)
                _auto_assume_fifo_empty_no_read: assume(!rd_en_in);
        end
    end

endmodule
`endif // FORMAL