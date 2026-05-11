// ═══════════════════════════════════════════════════════════════
// VeriAssist v2.0 — Example DUT: Synchronous FIFO
//
// Two variants controlled by `define:
//   Default (no define)  → Correct: guards wr_en when full
//   `define FIFO_BUG     → Buggy: allows write when full (overflow)
//
// Formal properties to verify:
//   1. No overflow: wr_en must never be active when full
//   2. No underflow: rd_en must never be active when empty
//   3. Full flag: asserted when count == DEPTH
//   4. Empty flag: asserted when count == 0
//   5. Count bounds: count never exceeds DEPTH
// ═══════════════════════════════════════════════════════════════

module sync_fifo #(
    parameter DEPTH = 8,
    parameter WIDTH = 8
)(
    input  wire             clk,
    input  wire             rst_n,

    // Write port
    input  wire             wr_en,
    input  wire [WIDTH-1:0] wr_data,

    // Read port
    input  wire             rd_en,
    output reg  [WIDTH-1:0] rd_data,

    // Status
    output wire             full,
    output wire             empty,
    output reg  [$clog2(DEPTH):0] count
);

    // Memory and pointers
    reg [WIDTH-1:0] mem [0:DEPTH-1];
    reg [$clog2(DEPTH)-1:0] wr_ptr;
    reg [$clog2(DEPTH)-1:0] rd_ptr;

    // Status flags
    assign full  = (count == DEPTH);
    assign empty = (count == 0);

    // ── Write Logic ──────────────────────────────────────
    always @(posedge clk) begin
        if (!rst_n) begin
            wr_ptr <= 0;
        end else begin
`ifdef FIFO_BUG
            // BUG: no full guard — allows write when full, causing overflow
            if (wr_en) begin
                mem[wr_ptr] <= wr_data;
                wr_ptr      <= wr_ptr + 1;
            end
`else
            // CORRECT: only write when not full
            if (wr_en && !full) begin
                mem[wr_ptr] <= wr_data;
                wr_ptr      <= wr_ptr + 1;
            end
`endif
        end
    end

    // ── Read Logic ───────────────────────────────────────
    always @(posedge clk) begin
        if (!rst_n) begin
            rd_ptr  <= 0;
            rd_data <= 0;
        end else begin
            if (rd_en && !empty) begin
                rd_data <= mem[rd_ptr];
                rd_ptr  <= rd_ptr + 1;
            end
        end
    end

    // ── Count Logic ──────────────────────────────────────
    always @(posedge clk) begin
        if (!rst_n) begin
            count <= 0;
        end else begin
`ifdef FIFO_BUG
            // BUG: count increments even when full
            case ({wr_en, rd_en && !empty})
                2'b10:   count <= count + 1;
                2'b01:   count <= count - 1;
                default: count <= count;
            endcase
`else
            // CORRECT: count only changes on valid operations
            case ({wr_en && !full, rd_en && !empty})
                2'b10:   count <= count + 1;
                2'b01:   count <= count - 1;
                default: count <= count;
            endcase
`endif
        end
    end

endmodule