// SVA assertions for the synchronous FIFO
// Yosys/sby-compatible: immediate assertions inside always @(posedge clk)
// No inline @(posedge clk) in property() — not supported by Yosys without Verific

module fifo_sva (
    input logic clk,
    input logic reset_n,
    input logic wr_en,
    input logic rd_en,
    input logic full,
    input logic empty
);

    // ── Previous-cycle registers (for |=> style checks) ────────────
    logic wr_en_d, rd_en_d, full_d, empty_d;
    always_ff @(posedge clk) begin
        wr_en_d <= wr_en;
        rd_en_d <= rd_en;
        full_d  <= full;
        empty_d <= empty;
    end

    // ── Assertions ─────────────────────────────────────────────────
    always @(posedge clk) begin
        if (reset_n) begin

            // Full and empty cannot both be true
            ap_fifo_not_full_empty: assert (!(full && empty));

            // After write (not full), FIFO must not be empty next cycle
            if (wr_en_d && !full_d)
                ap_fifo_write_not_empty: assert (!empty);

            // After read with no write (not empty), occupancy changes correctly
            if (rd_en_d && !empty_d && !wr_en_d)
                ap_fifo_empty_prev_read: assert (empty || !full);

            // Write to a full FIFO (no read) keeps full asserted
            if (wr_en_d && full_d && !rd_en_d)
                ap_fifo_full_stable_on_full_write: assert (full);

            // Read from empty FIFO (no write) keeps empty asserted
            if (rd_en_d && empty_d && !wr_en_d)
                ap_fifo_empty_stable_on_empty_read: assert (empty);

            // Simultaneous read+write (non-boundary) keeps occupancy unchanged
            if (wr_en_d && rd_en_d && !full_d && !empty_d)
                ap_fifo_rw_simultaneous: assert (!full && !empty);

        end
    end

    // After reset goes high, FIFO must be empty on the very next cycle
    always @(posedge clk) begin
        if ($rose(reset_n))
            ap_fifo_empty_after_reset: assert (empty);
    end

    // ── Cover properties ───────────────────────────────────────────
    always @(posedge clk) begin
        // FIFO reaches empty
        wp_fifo_empty: cover (reset_n && empty);

        // FIFO reaches full
        wp_fifo_full: cover (reset_n && full);

        // FIFO drains from full (full falls)
        wp_fifo_full_falling_edge: cover (reset_n && !full && full_d);
    end

endmodule

// Bind the checker onto every instance of the fifo module
bind fifo fifo_sva inst_fifo_sva (
    .clk     (clk),
    .reset_n (reset_n),
    .wr_en   (wr_en),
    .rd_en   (rd_en),
    .full    (full),
    .empty   (empty)
);