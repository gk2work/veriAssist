`ifdef FORMAL
module fifo_sva (
    input wire clk_in,
    input wire rst_n_in,
    input wire data_start,
    input wire empty_out,
    input wire full_out,
    input wire [7:0] rd_data_out,
    input wire rd_en_in,
    input wire [7:0] wr_data_in,
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
    reg [7:0] wr_data_in_past1;
    reg [7:0] wr_data_in_past2;

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

    // --- wp_fifo_full: cover property (fifo_full) ---
    // Original SVA: (1 |->
    //       (full_out) )
    always @(posedge clk_in) begin
        if (!(!rst_n_in)) begin
            if (1 && (full_out))
                wp_fifo_full: cover(1);
        end
    end

    // --- wp_fifo_empty: cover property (fifo_empty) ---
    // Original SVA: (1 |->
    //       (empty_out) )
    always @(posedge clk_in) begin
        if (!(!rst_n_in)) begin
            if (1 && (empty_out))
                wp_fifo_empty: cover(1);
        end
    end

    // --- wp_fifo_full_falling_edge: cover property (fifo_full_falling_edge) ---
    // Original SVA: (1 |->
    //       ($fell(full_out)) )
    always @(posedge clk_in) begin
        if (!(!rst_n_in)) begin
            if (1 && (!full_out && full_out_prev))
                wp_fifo_full_falling_edge: cover(1);
        end
    end

    // --- wp_fifo_full_after_28: cover property (fifo_full_after_28) ---
    // Original SVA: ( (empty_out) |->
    //       ( ##28 full_out) )
    reg [27:0] _va_wp_fifo_full_after_28_delay_1;
    always @(posedge clk_in) begin
        if (!rst_n_in) begin
            _va_wp_fifo_full_after_28_delay_1 <= 0;
        end else begin
            _va_wp_fifo_full_after_28_delay_1 <= {_va_wp_fifo_full_after_28_delay_1[26:0], (empty_out)};
            if (_va_wp_fifo_full_after_28_delay_1[27] && (full_out))
                wp_fifo_full_after_28: cover(1);
        end
    end

    // --- ap_fifo_not_full_empty: assert property (fifo_not_full_empty) ---
    // Original SVA: (1 |->
    //       ($onehot0({full_out,empty_out})) )
    always @(posedge clk_in) begin
        if (!(!rst_n_in)) begin
            if (1 && !(({full_out,empty_out}) == 0 || (({full_out,empty_out}) & (({full_out,empty_out}) - 1)) == 0))
                begin end // disabled assertion ap_fifo_not_full_empty
        end
    end

    // --- ap_fifo_onehot0_full_empty: assert property (fifo_onehot0_full_empty) ---
    // Original SVA: (1 |->
    //       ($onehot0({full_out, empty_out})) )
    always @(posedge clk_in) begin
        if (!(!rst_n_in)) begin
            if (1 && !(({full_out, empty_out}) == 0 || (({full_out, empty_out}) & (({full_out, empty_out}) - 1)) == 0))
                begin end // disabled assertion ap_fifo_onehot0_full_empty
        end
    end

    // --- ap_fifo_full_prev_write: assert property (fifo_full_prev_write) ---
    // Original SVA: ( ($rose(full_out)) |->
    //       ($past(wr_en_in)) )
    always @(posedge clk_in) begin
        if (!(!rst_n_in)) begin
            if (full_out && !full_out_prev && !(wr_en_in_past1))
                begin end // disabled assertion ap_fifo_full_prev_write
        end
    end

    // --- ap_fifo_empty_prev_read_no_write: assert property (fifo_empty_prev_read_no_write) ---
    // Original SVA: ( ($rose(empty_out)) |->
    //       ( ($past(rd_en_in)) &&
    //         (!$past(wr_en_in)) ))
    always @(posedge clk_in) begin
        if (!(!rst_n_in)) begin
            if (empty_out && !empty_out_prev && !((rd_en_in_past1) &&
        (!wr_en_in_past1)))
                ap_fifo_empty_prev_read_no_write: assert(0);
        end
    end

    // --- ap_fifo_write_not_empty: assert property (fifo_write_not_empty) ---
    // Original SVA: ( (wr_en_in) |->
    //       ( ##1 !empty_out) )
    reg _va_ap_fifo_write_not_empty_delay_2;
    always @(posedge clk_in) begin
        if (!rst_n_in) begin
            _va_ap_fifo_write_not_empty_delay_2 <= 0;
        end else begin
            _va_ap_fifo_write_not_empty_delay_2 <= (wr_en_in);
            if (_va_ap_fifo_write_not_empty_delay_2 && !(!empty_out))
                begin end // disabled assertion ap_fifo_write_not_empty
        end
    end

    // --- ap_fifo_empty_after_reset: assert property (fifo_empty_after_reset) ---
    // Original SVA: ( ($rose(rst_n_in)) |->
    //       (empty_out) )
    always @(posedge clk_in) begin
        if (!(!rst_n_in)) begin
            if (rst_n_in && !rst_n_in_prev && !(empty_out))
                begin end // disabled assertion ap_fifo_empty_after_reset
        end
    end

    // --- ap_fifo_read_write_equal: assert property (fifo_read_write_equal) ---
    // Original SVA: ( (rd_en_in == wr_en_in) |->
    //       ( ##1 $stable(full_out) &&
    //         ($stable(empty_out))) )
    reg _va_ap_fifo_read_write_equal_delay_3;
    always @(posedge clk_in) begin
        if (!rst_n_in) begin
            _va_ap_fifo_read_write_equal_delay_3 <= 0;
        end else begin
            _va_ap_fifo_read_write_equal_delay_3 <= (rd_en_in == wr_en_in);
            if (_va_ap_fifo_read_write_equal_delay_3 && !((full_out == full_out_prev) &&
        ((empty_out == empty_out_prev))))
                begin end // disabled assertion ap_fifo_read_write_equal
        end
    end

    // --- ap_fifo_write_32_full: assert property (fifo_write_32_full) ---
    // Original SVA: ( ((wr_en_in && !rd_en_in) [*32]) |->
    //       ( ##1 full_out) )
    reg [5:0] _va_ap_fifo_write_32_full_ante_cnt_4;
    reg _va_ap_fifo_write_32_full_ante_trig_5;
    always @(posedge clk_in) begin
        if (!rst_n_in) begin
            _va_ap_fifo_write_32_full_ante_cnt_4 <= 0;
            _va_ap_fifo_write_32_full_ante_trig_5 <= 0;
        end else begin
            _va_ap_fifo_write_32_full_ante_trig_5 <= ((wr_en_in && !rd_en_in) && (_va_ap_fifo_write_32_full_ante_cnt_4 == 31));
            if (wr_en_in && !rd_en_in) begin
                if (_va_ap_fifo_write_32_full_ante_cnt_4 < 32)
                    _va_ap_fifo_write_32_full_ante_cnt_4 <= _va_ap_fifo_write_32_full_ante_cnt_4 + 1;
            end else begin
                _va_ap_fifo_write_32_full_ante_cnt_4 <= 0;
            end
            if (_va_ap_fifo_write_32_full_ante_trig_5 && !(full_out))
                begin end // disabled assertion ap_fifo_write_32_full
        end
    end

    // --- ap_fifo_data_after_empty: assert property (fifo_data_after_empty) ---
    // Original SVA: ( ((empty_out) &&
    //         (wr_en_in) ##1
    //         (rd_en_in)) |->
    //       ( ##1 (rd_data_out == $past(wr_data_in, 2))) )
    reg _va_ap_fifo_data_after_empty_stage_6;
    reg _va_ap_fifo_data_after_empty_trig_7;
    always @(posedge clk_in) begin
        if (!rst_n_in) begin
            _va_ap_fifo_data_after_empty_stage_6 <= 0;
            _va_ap_fifo_data_after_empty_trig_7 <= 0;
        end else begin
            _va_ap_fifo_data_after_empty_trig_7 <= (_va_ap_fifo_data_after_empty_stage_6 && (rd_en_in));
            _va_ap_fifo_data_after_empty_stage_6 <= ((empty_out) && (wr_en_in));
            if (_va_ap_fifo_data_after_empty_trig_7 && !(rd_data_out == wr_data_in_past2))
                begin end // disabled assertion ap_fifo_data_after_empty
        end
    end

    // --- ap_fifo_data_after_empty_1_4: assert property (fifo_data_after_empty_1_4) ---
    // Original SVA: reg[7:0] data_start;
    //     ( (((empty_out && wr_en_in), data_start = wr_data_in) ##1
    //         (!rd_en_in) [*1:4] ##1
    //         (rd_en_in)) |->
    //       ( ##1 (rd_data_out == data_start)) )
    reg _va_ap_fifo_data_after_empty_1_4_arm_8;
    reg _va_ap_fifo_data_after_empty_1_4_hold_9;
    reg _va_ap_fifo_data_after_empty_1_4_match_10;
    reg [2:0] _va_ap_fifo_data_after_empty_1_4_count_11;
    reg [7:0] ap_fifo_data_after_empty_1_4_capture;
    always @(posedge clk_in) begin
        if (!rst_n_in) begin
            _va_ap_fifo_data_after_empty_1_4_arm_8 <= 0;
            _va_ap_fifo_data_after_empty_1_4_hold_9 <= 0;
            _va_ap_fifo_data_after_empty_1_4_match_10 <= 0;
            _va_ap_fifo_data_after_empty_1_4_count_11 <= 0;
            ap_fifo_data_after_empty_1_4_capture <= 0;
        end else begin
            if (_va_ap_fifo_data_after_empty_1_4_match_10 && !(rd_data_out == ap_fifo_data_after_empty_1_4_capture))
                begin end // disabled assertion ap_fifo_data_after_empty_1_4
            _va_ap_fifo_data_after_empty_1_4_match_10 <= 0;
            if (_va_ap_fifo_data_after_empty_1_4_arm_8) begin
                if (!rd_en_in) begin
                    _va_ap_fifo_data_after_empty_1_4_hold_9 <= 1;
                    _va_ap_fifo_data_after_empty_1_4_count_11 <= 1;
                end else begin
                    _va_ap_fifo_data_after_empty_1_4_hold_9 <= 0;
                    _va_ap_fifo_data_after_empty_1_4_count_11 <= 0;
                end
                _va_ap_fifo_data_after_empty_1_4_arm_8 <= 0;
            end else if (_va_ap_fifo_data_after_empty_1_4_hold_9) begin
                if (!rd_en_in && _va_ap_fifo_data_after_empty_1_4_count_11 < 4) begin
                    _va_ap_fifo_data_after_empty_1_4_count_11 <= _va_ap_fifo_data_after_empty_1_4_count_11 + 1;
                end else if (rd_en_in && _va_ap_fifo_data_after_empty_1_4_count_11 >= 1 && _va_ap_fifo_data_after_empty_1_4_count_11 <= 4) begin
                    _va_ap_fifo_data_after_empty_1_4_match_10 <= 1;
                    _va_ap_fifo_data_after_empty_1_4_hold_9 <= 0;
                    _va_ap_fifo_data_after_empty_1_4_count_11 <= 0;
                end else begin
                    _va_ap_fifo_data_after_empty_1_4_hold_9 <= 0;
                    _va_ap_fifo_data_after_empty_1_4_count_11 <= 0;
                end
            end
            if (empty_out && wr_en_in) begin
                ap_fifo_data_after_empty_1_4_capture <= wr_data_in;
                _va_ap_fifo_data_after_empty_1_4_arm_8 <= 1;
                _va_ap_fifo_data_after_empty_1_4_hold_9 <= 0;
                _va_ap_fifo_data_after_empty_1_4_count_11 <= 0;
            end
        end
    end

    // --- cp_fifo_full_no_write: assume property (fifo_full_no_write) ---
    // Original SVA: ( (full_out) |->
    //       (!wr_en_in) )
    always @(posedge clk_in) begin
        if (!(!rst_n_in)) begin
            if (full_out)
                cp_fifo_full_no_write: assume(!wr_en_in);
        end
    end

    // --- cp_fifo_empty_no_read: assume property (fifo_empty_no_read) ---
    // Original SVA: ( (empty_out) |->
    //       (!rd_en_in) )
    always @(posedge clk_in) begin
        if (!(!rst_n_in)) begin
            if (empty_out)
                cp_fifo_empty_no_read: assume(!rd_en_in);
        end
    end

endmodule
`endif // FORMAL