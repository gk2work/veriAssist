// SVA assertions for the synchronous FIFO
// Compatible with SymbiYosys / Yosys formal verification
// Uses default clocking (no inline @(posedge clk) in properties)

module fifo_sva (
    input logic clk,
    input logic reset_n,
    input logic wr_en,
    input logic rd_en,
    input logic full,
    input logic empty
);

    // Yosys requires clocking and disable to be declared at module level
    default clocking cb @(posedge clk); endclocking
    default disable iff (!reset_n);

    // ── Cover properties ─────────────────────────────────────────

    // FIFO can reach empty state
    wp_fifo_empty: cover property (empty);

    // FIFO can reach full state
    wp_fifo_full: cover property (full);

    // FIFO can go from full back to not-full (drains)
    wp_fifo_full_falling_edge: cover property ($fell(full));

    // ── Assertions ───────────────────────────────────────────────

    // FIFO cannot be simultaneously full and empty
    ap_fifo_not_full_empty: assert property (
        !(full && empty)
    );

    // After reset deasserts, FIFO must be empty on next cycle
    ap_fifo_empty_after_reset: assert property (
        $rose(reset_n) |=> empty
    );

    // Write when not full implies not-empty next cycle
    ap_fifo_write_not_empty: assert property (
        (wr_en && !full) |=> !empty
    );

    // Read when not empty (no simultaneous write) implies occupancy changes correctly
    ap_fifo_empty_prev_read: assert property (
        (rd_en && !empty && !wr_en) |=> (empty || !full)
    );

    // Full flag must be stable when writing to an already-full FIFO (no rd)
    ap_fifo_full_stable_on_full_write: assert property (
        (wr_en && full && !rd_en) |=> full
    );

    // Empty flag must be stable when reading an already-empty FIFO (no wr)
    ap_fifo_empty_stable_on_empty_read: assert property (
        (rd_en && empty && !wr_en) |=> empty
    );

    // Simultaneous read+write on non-boundary FIFO keeps occupancy unchanged
    ap_fifo_rw_simultaneous: assert property (
        (wr_en && rd_en && !full && !empty) |=> (!full && !empty)
    );

    // Full and empty cannot both be true (explicit mutual exclusion)
    ap_fifo_onehot0_full_empty: assert property (
        !(full && empty)
    );

endmodule

// Bind the SVA checker onto every instance of the fifo module
bind fifo fifo_sva inst_fifo_sva (
    .clk     (clk),
    .reset_n (reset_n),
    .wr_en   (wr_en),
    .rd_en   (rd_en),
    .full    (full),
    .empty   (empty)
);