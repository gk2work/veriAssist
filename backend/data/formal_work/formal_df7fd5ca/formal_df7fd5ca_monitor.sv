`ifdef FORMAL
module fifo (
    input wire clk,
    input wire rst_n_in,
    input wire data_start,
    input wire empty_out,
    input wire fell,
    input wire full_out,
    input wire onehot0,
    input wire past,
    input wire rd_data_out,
    input wire rd_en_in,
    input wire rose,
    input wire stable,
    input wire wr_data_in,
    input wire wr_en_in
);

    // Past-value registers for edge/stability detection
    reg empty_out_prev;
    reg full_out_prev;
    reg rst_n_in_prev;

    always @(posedge clk) begin
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

    always @(posedge clk) begin
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

    // --- test1: assume property (fifo_empty_no_read) ---
    // Original SVA: ( (empty_out)|->(!rd_en_in) )
    always @(posedge clk) begin
        if (!(!rst_n_in)) begin
            if ((empty_out)
                test1: assume((!rd_en_in) ));
        end
    end

    // --- _auto_cover_fifo_full: cover property (fifo_full) ---
    // Original SVA: (1|->(full_out) )
    always @(posedge clk) begin
        if (!(!rst_n_in)) begin
            if ((1 && ((full_out) )))
                _auto_cover_fifo_full: cover(1);
        end
    end

    // --- _auto_cover_fifo_empty: cover property (fifo_empty) ---
    // Original SVA: (1|->(empty_out) )
    always @(posedge clk) begin
        if (!(!rst_n_in)) begin
            if ((1 && ((empty_out) )))
                _auto_cover_fifo_empty: cover(1);
        end
    end

    // --- _auto_cover_fifo_full_falling_edge: cover property (fifo_full_falling_edge) ---
    // Original SVA: (1 |->($fell(full_out)) )
    always @(posedge clk) begin
        if (!(!rst_n_in)) begin
            if ((1 && (((!full_out && full_out_prev)) )))
                _auto_cover_fifo_full_falling_edge: cover(1);
        end
    end

    // --- _auto_cover_fifo_full_after_28: cover property (fifo_full_after_28) ---
    // Original SVA: ( (empty_out)|->( ##28 full_out) )
    reg [27:0] _va__auto_cover_fifo_full_after_28_delay_1;
    always @(posedge clk) begin
        if (!rst_n_in) begin
            _va__auto_cover_fifo_full_after_28_delay_1 <= 0;
        end else begin
            _va__auto_cover_fifo_full_after_28_delay_1 <= {_va__auto_cover_fifo_full_after_28_delay_1[26:0], (( (empty_out))};
            if (_va__auto_cover_fifo_full_after_28_delay_1[27] && (( full_out) )))
                _auto_cover_fifo_full_after_28: cover(1);
        end
    end

    // --- _auto_assert_fifo_not_full_empty: assert property (fifo_not_full_empty) ---
    // Original SVA: (1|->($onehot0({full_out,empty_out})) )
    always @(posedge clk) begin
        if (!(!rst_n_in)) begin
            if ((1 && !(((({full_out,empty_out}) == 0 || (({full_out,empty_out}) & (({full_out,empty_out}) - 1)) == 0)) )))
                _auto_assert_fifo_not_full_empty: assert(0);
        end
    end

    // --- _auto_assert_fifo_onehot0_full_empty: assert property (fifo_onehot0_full_empty) ---
    // Original SVA: (1|->($onehot0({full_out, empty_out})) )
    always @(posedge clk) begin
        if (!(!rst_n_in)) begin
            if ((1 && !(((({full_out, empty_out}) == 0 || (({full_out, empty_out}) & (({full_out, empty_out}) - 1)) == 0)) )))
                _auto_assert_fifo_onehot0_full_empty: assert(0);
        end
    end

    // --- _auto_assert_fifo_full_prev_write: assert property (fifo_full_prev_write) ---
    // Original SVA: ( ($rose(full_out))|->($past(wr_en_in)) )
    always @(posedge clk) begin
        if (!(!rst_n_in)) begin
            if ((full_out && !full_out_prev && !((wr_en_in_past1) )))
                _auto_assert_fifo_full_prev_write: assert(0);
        end
    end

    // --- _auto_assert_fifo_empty_prev_read_no_write: assert property (fifo_empty_prev_read_no_write) ---
    // Original SVA: ( ($rose(empty_out))|->( ($past(rd_en_in)) &&(!$past(wr_en_in)) ))
    always @(posedge clk) begin
        if (!(!rst_n_in)) begin
            if ((empty_out && !empty_out_prev && !(( (rd_en_in_past1) &&(!wr_en_in_past1) ))))
                _auto_assert_fifo_empty_prev_read_no_write: assert(0);
        end
    end

    // --- _auto_assert_fifo_write_not_empty: assert property (fifo_write_not_empty) ---
    // Original SVA: ( (wr_en_in)|->(  !empty_out) )
    always @(posedge clk) begin
        if (!(!rst_n_in)) begin
            if ((wr_en_in && !((  !empty_out) )))
                _auto_assert_fifo_write_not_empty: assert(0);
        end
    end

    // --- _auto_assert_fifo_empty_after_reset: assert property (fifo_empty_after_reset) ---
    // Original SVA: ( ($rose(rst_n_in))|->(empty_out) )
    always @(posedge clk) begin
        if (!(!rst_n_in)) begin
            if ((rst_n_in && !rst_n_in_prev && !((empty_out) )))
                _auto_assert_fifo_empty_after_reset: assert(0);
        end
    end

    // --- _auto_assert_fifo_read_write_equal: assert property (fifo_read_write_equal) ---
    // Original SVA: ( (rd_en_in == wr_en_in)|->( ##1 $stable(full_out) &&($stable(empty_out))) )
    reg [0:0] _va__auto_assert_fifo_read_write_equal_delay_2;
    always @(posedge clk) begin
        if (!rst_n_in) begin
            _va__auto_assert_fifo_read_write_equal_delay_2 <= 0;
        end else begin
            _va__auto_assert_fifo_read_write_equal_delay_2 <= {_va__auto_assert_fifo_read_write_equal_delay_2[-1:0], (( (rd_en_in == wr_en_in))};
            if (_va__auto_assert_fifo_read_write_equal_delay_2[0] && !(( (full_out == full_out_prev) &&((empty_out == empty_out_prev))) )))
                _auto_assert_fifo_read_write_equal: assert(0); // FAIL at delay 1
        end
    end

    // --- _auto_assert_fifo_write_32_full: assert property (fifo_write_32_full) ---
    // Original SVA: ( ((wr_en_in && !rd_en_in) [*32])|->( ##1 full_out) )
    reg [0:0] _va__auto_assert_fifo_write_32_full_delay_3;
    always @(posedge clk) begin
        if (!rst_n_in) begin
            _va__auto_assert_fifo_write_32_full_delay_3 <= 0;
        end else begin
            _va__auto_assert_fifo_write_32_full_delay_3 <= {_va__auto_assert_fifo_write_32_full_delay_3[-1:0], (( ((wr_en_in && !rd_en_in) [*32]))};
            if (_va__auto_assert_fifo_write_32_full_delay_3[0] && !(( full_out) )))
                _auto_assert_fifo_write_32_full: assert(0); // FAIL at delay 1
        end
    end

    // --- _auto_assert_fifo_data_after_empty: assert property (fifo_data_after_empty) ---
    // Original SVA: ( ((empty_out) &&(wr_en_in) ##1 (rd_en_in))|-> ( ##1 (rd_data_out == $past(wr_data_in, 2))) )
    reg [0:0] _va__auto_assert_fifo_data_after_empty_delay_4;
    always @(posedge clk) begin
        if (!rst_n_in) begin
            _va__auto_assert_fifo_data_after_empty_delay_4 <= 0;
        end else begin
            _va__auto_assert_fifo_data_after_empty_delay_4 <= {_va__auto_assert_fifo_data_after_empty_delay_4[-1:0], (( ((empty_out) &&(wr_en_in) ##1 (rd_en_in)))};
            if (_va__auto_assert_fifo_data_after_empty_delay_4[0] && !(( (rd_data_out == wr_data_in_past2)) )))
                _auto_assert_fifo_data_after_empty: assert(0); // FAIL at delay 1
        end
    end

    // --- _auto_assert_fifo_data_after_empty_1_4: assert property (fifo_data_after_empty_1_4) ---
    // Original SVA: reg[7:0] data_start;
    ( (((empty_out && wr_en_in), data_start = wr_data_in) ##1(!rd_en_in) [*1:4] ##1 (rd_en_in)) |-> ( ##1 (rd_data_out == data_start)) )
    reg [0:0] _va__auto_assert_fifo_data_after_empty_1_4_delay_5;
    always @(posedge clk) begin
        if (!rst_n_in) begin
            _va__auto_assert_fifo_data_after_empty_1_4_delay_5 <= 0;
        end else begin
            _va__auto_assert_fifo_data_after_empty_1_4_delay_5 <= {_va__auto_assert_fifo_data_after_empty_1_4_delay_5[-1:0], (reg[7:0] data_start;
    ( (((empty_out && wr_en_in), data_start = wr_data_in) ##1(!rd_en_in) [*1:4] ##1 (rd_en_in)))};
            if (_va__auto_assert_fifo_data_after_empty_1_4_delay_5[0] && !(( (rd_data_out == data_start)) )))
                _auto_assert_fifo_data_after_empty_1_4: assert(0); // FAIL at delay 1
        end
    end

    // --- _auto_assume_fifo_full_no_write: assume property (fifo_full_no_write) ---
    // Original SVA: ( (full_out)|->(!wr_en_in) )
    always @(posedge clk) begin
        if (!(!rst_n_in)) begin
            if ((full_out)
                _auto_assume_fifo_full_no_write: assume((!wr_en_in) ));
        end
    end

endmodule
`endif // FORMAL