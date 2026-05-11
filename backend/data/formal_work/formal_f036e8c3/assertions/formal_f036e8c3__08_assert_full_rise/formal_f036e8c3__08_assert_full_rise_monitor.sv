`ifdef FORMAL
module fifo_checker (
    input wire clk,
    input wire rst_n,
    input wire wr_en,
    input wire rd_en,
    input wire [7:0] wr_data,
    input wire [7:0] rd_data,
    input wire full,
    input wire empty,
    input wire [3:0] count
);

    // Past-value registers for edge/stability detection
    reg [3:0] count_prev;
    reg empty_prev;
    reg full_prev;

    always @(posedge clk) begin
        if (!rst_n) begin
            count_prev <= 0;
            empty_prev <= 0;
            full_prev <= 0;
        end else begin
            count_prev <= count;
            empty_prev <= empty;
            full_prev <= full;
        end
    end

    // $past delay registers (shift chains)
    reg [3:0] count_past1;
    reg wr_en_past1;
    reg rd_en_past1;

    always @(posedge clk) begin
        if (!rst_n) begin
            count_past1 <= 0;
            wr_en_past1 <= 0;
            rd_en_past1 <= 0;
        end else begin
            count_past1 <= count;
            wr_en_past1 <= wr_en;
            rd_en_past1 <= rd_en;
        end
    end

    // --- assert_not_full_and_empty: assert property (p_not_full_and_empty) ---
    // Original SVA: !(full && empty)
    always @(posedge clk) begin
        if (!(!rst_n)) begin
            begin end // disabled assertion assert_not_full_and_empty
        end
    end

    // --- assert_empty_zero: assert property (p_empty_when_zero) ---
    // Original SVA: (count == 0) |-> empty
    always @(posedge clk) begin
        if (!(!rst_n)) begin
            if (count == 0 && !(empty))
                begin end // disabled assertion assert_empty_zero
        end
    end

    // --- assert_full_max: assert property (p_full_when_max) ---
    // Original SVA: (count == 8) |-> full
    always @(posedge clk) begin
        if (!(!rst_n)) begin
            if (count == 8 && !(full))
                begin end // disabled assertion assert_full_max
        end
    end

    // --- assert_write_inc: assert property (p_write_increments) ---
    // Original SVA: (wr_en && !full && !rd_en) |=> (count == $past(count) + 1)
    reg _va_assert_write_inc_triggered_1;
    always @(posedge clk) begin
        if (!rst_n) begin
            _va_assert_write_inc_triggered_1 <= 0;
        end else begin
            if (_va_assert_write_inc_triggered_1 && !(count == count_past1 + 1))
                begin end // disabled assertion assert_write_inc
            _va_assert_write_inc_triggered_1 <= (wr_en && !full && !rd_en);
        end
    end

    // --- assume_no_write_full: assume property (p_no_write_when_full) ---
    // Original SVA: full |-> !wr_en
    always @(posedge clk) begin
        if (!(!rst_n)) begin
            if (full)
                assume_no_write_full: assume(!wr_en);
        end
    end

    // --- assert_read_dec: assert property (p_read_decrements) ---
    // Original SVA: (rd_en && !empty && !wr_en) |=> (count == $past(count) - 1)
    reg _va_assert_read_dec_triggered_2;
    always @(posedge clk) begin
        if (!rst_n) begin
            _va_assert_read_dec_triggered_2 <= 0;
        end else begin
            if (_va_assert_read_dec_triggered_2 && !(count == count_past1 - 1))
                begin end // disabled assertion assert_read_dec
            _va_assert_read_dec_triggered_2 <= (rd_en && !empty && !wr_en);
        end
    end

    // --- assume_no_read_empty: assume property (p_no_read_when_empty) ---
    // Original SVA: empty |-> !rd_en
    always @(posedge clk) begin
        if (!(!rst_n)) begin
            if (empty)
                assume_no_read_empty: assume(!rd_en);
        end
    end

    // --- assert_count_bounded: assert property (p_count_bounded) ---
    // Original SVA: (count <= 8)
    always @(posedge clk) begin
        if (!(!rst_n)) begin
            begin end // disabled assertion assert_count_bounded
        end
    end

    // --- assert_count_pos: assert property (p_count_non_negative) ---
    // Original SVA: (count >= 0)
    always @(posedge clk) begin
        if (!(!rst_n)) begin
            begin end // disabled assertion assert_count_pos
        end
    end

    // --- assert_full_rise: assert property (p_full_rise_after_write) ---
    // Original SVA: $rose(full) |-> $past(wr_en)
    always @(posedge clk) begin
        if (!(!rst_n)) begin
            if (full && !full_prev && !(wr_en_past1))
                assert_full_rise: assert(0);
        end
    end

    // --- assert_empty_rise: assert property (p_empty_rise_after_read) ---
    // Original SVA: $rose(empty) |-> $past(rd_en)
    always @(posedge clk) begin
        if (!(!rst_n)) begin
            if (empty && !empty_prev && !(rd_en_past1))
                begin end // disabled assertion assert_empty_rise
        end
    end

    // --- assert_count_stable: assert property (p_count_stable_no_activity) ---
    // Original SVA: (!wr_en && !rd_en) |=> $stable(count)
    reg _va_assert_count_stable_triggered_3;
    always @(posedge clk) begin
        if (!rst_n) begin
            _va_assert_count_stable_triggered_3 <= 0;
        end else begin
            if (_va_assert_count_stable_triggered_3 && !(count == count_prev))
                begin end // disabled assertion assert_count_stable
            _va_assert_count_stable_triggered_3 <= (!wr_en && !rd_en);
        end
    end

    // WARNING: property 'full' not found for cover_full
    // WARNING: property 'empty' not found for cover_empty
endmodule
`endif // FORMAL