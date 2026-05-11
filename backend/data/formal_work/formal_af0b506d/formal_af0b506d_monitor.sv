`ifdef FORMAL
module fifo_sva (
    input wire clk,
    input wire rst,
    input wire empty,
    input wire fifo_count,
    input wire full,
    input wire rd_en,
    input wire wr_en
);

    // $past delay registers (shift chains)
    reg fifo_count_past1;

    always @(posedge clk) begin
        if (rst) begin
            fifo_count_past1 <= 0;
        end else begin
            fifo_count_past1 <= fifo_count;
        end
    end

    // --- _auto_assert_no_write_when_full: assert property (no_write_when_full) ---
    // Original SVA: full |-> !wr_en
    always @(posedge clk) begin
        if (!(rst)) begin
            if (full && !(!wr_en))
                _auto_assert_no_write_when_full: assert(0);
        end
    end

    // --- _auto_assert_no_read_when_empty: assert property (no_read_when_empty) ---
    // Original SVA: empty |-> !rd_en
    always @(posedge clk) begin
        if (!(rst)) begin
            if (empty && !(!rd_en))
                _auto_assert_no_read_when_empty: assert(0);
        end
    end

    // --- _auto_assert_write_increments_count: assert property (write_increments_count) ---
    // Original SVA: (wr_en && !full) |=> 
            fifo_count == $past(fifo_count) + 1
    reg _va__auto_assert_write_increments_count_triggered_1;
    always @(posedge clk) begin
        if (rst) begin
            _va__auto_assert_write_increments_count_triggered_1 <= 0;
        end else begin
            if (_va__auto_assert_write_increments_count_triggered_1 && !(fifo_count == fifo_count_past1 + 1))
                _auto_assert_write_increments_count: assert(0); // FAIL: consequent not met after antecedent
            _va__auto_assert_write_increments_count_triggered_1 <= (wr_en && !full);
        end
    end

    // --- _auto_assert_read_decrements_count: assert property (read_decrements_count) ---
    // Original SVA: (rd_en && !empty) |=> 
            fifo_count == $past(fifo_count) - 1
    reg _va__auto_assert_read_decrements_count_triggered_2;
    always @(posedge clk) begin
        if (rst) begin
            _va__auto_assert_read_decrements_count_triggered_2 <= 0;
        end else begin
            if (_va__auto_assert_read_decrements_count_triggered_2 && !(fifo_count == fifo_count_past1 - 1))
                _auto_assert_read_decrements_count: assert(0); // FAIL: consequent not met after antecedent
            _va__auto_assert_read_decrements_count_triggered_2 <= (rd_en && !empty);
        end
    end

    // --- _auto_assert_not_full_and_empty: assert property (not_full_and_empty) ---
    // Original SVA: !(full && empty)
    always @(posedge clk) begin
        if (!(rst)) begin
            _auto_assert_not_full_and_empty: assert(!(full && empty));
        end
    end

    // --- _auto_assert_reset_empty: assert property (reset_empty) ---
    // Original SVA: rst |-> empty
    always @(posedge clk) begin
        if (!(rst)) begin
            if (rst && !(empty))
                _auto_assert_reset_empty: assert(0);
        end
    end

    // WARNING: property 'full' not found for _auto_cover_full
endmodule
`endif // FORMAL