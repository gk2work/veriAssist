// SVA assertions for the synchronous FIFO
// Bind to: fifo (top module)
// Clock: clk   Reset: reset_n (active-low)

module fifo_sva (
    input logic       clk,
    input logic       reset_n,
    input logic       wr_en,
    input logic       rd_en,
    input logic       full,
    input logic       empty
);

    // ── Covers ──────────────────────────────────────────────────

    // FIFO reaches empty state
    wp_fifo_empty: cover property (
        @(posedge clk) disable iff (!reset_n)
        empty
    );

    // FIFO reaches full state
    wp_fifo_full: cover property (
        @(posedge clk) disable iff (!reset_n)
        full
    );

    // Full flag falls (FIFO drains from full)
    wp_fifo_full_falling_edge: cover property (
        @(posedge clk) disable iff (!reset_n)
        $rose(!full) && $stable(reset_n)
    );

    // ── Assertions ───────────────────────────────────────────────

    // FIFO cannot be simultaneously full and empty
    ap_fifo_not_full_empty: assert property (
        @(posedge clk) disable iff (!reset_n)
        !(full && empty)
    );

    // After reset, FIFO must be empty
    ap_fifo_empty_after_reset: assert property (
        @(posedge clk)
        $rose(reset_n) |=> empty
    );

    // A write when not full means FIFO is not empty next cycle
    ap_fifo_write_not_empty: assert property (
        @(posedge clk) disable iff (!reset_n)
        (wr_en && !full) |=> !empty
    );

    // A read when not empty and no simultaneous write means FIFO
    // is either still not empty or becomes empty next cycle
    ap_fifo_empty_prev_read: assert property (
        @(posedge clk) disable iff (!reset_n)
        (rd_en && !empty && !wr_en) |=> (empty || !full)
    );

    // Full and empty cannot both be true simultaneously (explicit one-hot0)
    ap_fifo_onehot0_full_empty: assert property (
        @(posedge clk) disable iff (!reset_n)
        !(full && empty)
    );

    // Write enable asserted on a full FIFO must not change full flag
    ap_fifo_full_stable_on_full_write: assert property (
        @(posedge clk) disable iff (!reset_n)
        (wr_en && full && !rd_en) |=> full
    );

    // Read enable asserted on an empty FIFO must not change empty flag
    ap_fifo_empty_stable_on_empty_read: assert property (
        @(posedge clk) disable iff (!reset_n)
        (rd_en && empty && !wr_en) |=> empty
    );

    // Simultaneous read and write on non-empty/non-full FIFO keeps
    // occupancy the same (full and empty unchanged)
    ap_fifo_rw_simultaneous: assert property (
        @(posedge clk) disable iff (!reset_n)
        (wr_en && rd_en && !full && !empty) |=> (!full && !empty)
    );

endmodule

// Bind the SVA checker to the DUT instance
bind fifo fifo_sva inst_fifo_sva (
    .clk     (clk),
    .reset_n (reset_n),
    .wr_en   (wr_en),
    .rd_en   (rd_en),
    .full    (full),
    .empty   (empty)
);