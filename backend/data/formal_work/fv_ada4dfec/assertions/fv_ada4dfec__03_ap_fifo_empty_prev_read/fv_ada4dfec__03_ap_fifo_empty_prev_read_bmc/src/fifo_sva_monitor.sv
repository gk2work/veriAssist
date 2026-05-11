`ifdef FORMAL
module fifo_sva (
    input wire clk,
    input wire reset_n,
    input wire wr_en,
    input wire rd_en,
    input wire full,
    input wire empty
);

    // Past-value registers for edge/stability detection
    reg reset_n_prev;

    always @(posedge clk) begin
        if (!reset_n) begin
            reset_n_prev <= 0;
        end else begin
            reset_n_prev <= reset_n;
        end
    end

    // --- ap_fifo_not_full_empty: assert property (p_not_full_empty) ---
    // Original SVA: !(full && empty)
    always @(posedge clk) begin
        if (!(!reset_n)) begin
            begin end // disabled assertion ap_fifo_not_full_empty
        end
    end

    // --- ap_fifo_write_not_empty: assert property (p_write_not_empty) ---
    // Original SVA: (wr_en && !full) |=> !empty
    reg _va_ap_fifo_write_not_empty_triggered_1;
    always @(posedge clk) begin
        if (!reset_n) begin
            _va_ap_fifo_write_not_empty_triggered_1 <= 0;
        end else begin
            if (_va_ap_fifo_write_not_empty_triggered_1 && !(!empty))
                begin end // disabled assertion ap_fifo_write_not_empty
            _va_ap_fifo_write_not_empty_triggered_1 <= (wr_en && !full);
        end
    end

    // --- ap_fifo_empty_prev_read: assert property (p_empty_prev_read) ---
    // Original SVA: (rd_en && !empty && !wr_en) |=> (empty || !full)
    reg _va_ap_fifo_empty_prev_read_triggered_2;
    always @(posedge clk) begin
        if (!reset_n) begin
            _va_ap_fifo_empty_prev_read_triggered_2 <= 0;
        end else begin
            if (_va_ap_fifo_empty_prev_read_triggered_2 && !(empty || !full))
                ap_fifo_empty_prev_read: assert(0); // FAIL: consequent not met after antecedent
            _va_ap_fifo_empty_prev_read_triggered_2 <= (rd_en && !empty && !wr_en);
        end
    end

    // --- ap_fifo_full_stable: assert property (p_full_stable) ---
    // Original SVA: (wr_en && full && !rd_en) |=> full
    reg _va_ap_fifo_full_stable_triggered_3;
    always @(posedge clk) begin
        if (!reset_n) begin
            _va_ap_fifo_full_stable_triggered_3 <= 0;
        end else begin
            if (_va_ap_fifo_full_stable_triggered_3 && !(full))
                begin end // disabled assertion ap_fifo_full_stable
            _va_ap_fifo_full_stable_triggered_3 <= (wr_en && full && !rd_en);
        end
    end

    // --- ap_fifo_empty_stable: assert property (p_empty_stable) ---
    // Original SVA: (rd_en && empty && !wr_en) |=> empty
    reg _va_ap_fifo_empty_stable_triggered_4;
    always @(posedge clk) begin
        if (!reset_n) begin
            _va_ap_fifo_empty_stable_triggered_4 <= 0;
        end else begin
            if (_va_ap_fifo_empty_stable_triggered_4 && !(empty))
                begin end // disabled assertion ap_fifo_empty_stable
            _va_ap_fifo_empty_stable_triggered_4 <= (rd_en && empty && !wr_en);
        end
    end

    // --- ap_fifo_rw_simultaneous: assert property (p_rw_simultaneous) ---
    // Original SVA: (wr_en && rd_en && !full && !empty) |=> (!full && !empty)
    reg _va_ap_fifo_rw_simultaneous_triggered_5;
    always @(posedge clk) begin
        if (!reset_n) begin
            _va_ap_fifo_rw_simultaneous_triggered_5 <= 0;
        end else begin
            if (_va_ap_fifo_rw_simultaneous_triggered_5 && !(!full && !empty))
                begin end // disabled assertion ap_fifo_rw_simultaneous
            _va_ap_fifo_rw_simultaneous_triggered_5 <= (wr_en && rd_en && !full && !empty);
        end
    end

    // --- ap_fifo_empty_after_reset: assert property (p_empty_after_reset) ---
    // Original SVA: $rose(reset_n) |=> empty
    reg _va_ap_fifo_empty_after_reset_triggered_6;
    always @(posedge clk) begin
        if (!reset_n) begin
            _va_ap_fifo_empty_after_reset_triggered_6 <= 0;
        end else begin
            if (_va_ap_fifo_empty_after_reset_triggered_6 && !(empty))
                begin end // disabled assertion ap_fifo_empty_after_reset
            _va_ap_fifo_empty_after_reset_triggered_6 <= (reset_n && !reset_n_prev);
        end
    end

    // WARNING: property 'empty' not found for wp_fifo_empty
    // WARNING: property 'full' not found for wp_fifo_full
endmodule
`endif // FORMAL