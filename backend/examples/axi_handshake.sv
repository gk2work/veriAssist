// ═══════════════════════════════════════════════════════════════
// VeriAssist v2.0 — Example DUT: AXI-Lite Write Channel Slave
//
// Two variants controlled by `define:
//   Default (no define)  → Correct implementation
//   `define AXI_BUG      → Buggy: awready never asserts
//
// Formal properties to verify:
//   1. AWVALID stability: once asserted, stays high until AWREADY
//   2. AWREADY response: must respond within 8 cycles
//   3. WDATA stability: data stable while WVALID && !WREADY
// ═══════════════════════════════════════════════════════════════

module axi_slave (
    input  wire        clk,
    input  wire        rst_n,

    // Write address channel
    input  wire        awvalid,
    output reg         awready,
    input  wire [31:0] awaddr,

    // Write data channel
    input  wire        wvalid,
    output reg         wready,
    input  wire [31:0] wdata,
    input  wire [3:0]  wstrb,

    // Write response channel
    output reg         bvalid,
    input  wire        bready,
    output reg  [1:0]  bresp
);

    // Internal state
    reg [3:0] aw_wait_cnt;
    reg       aw_pending;
    reg       w_pending;

    // ── Write Address Channel ────────────────────────────
    always @(posedge clk) begin
        if (!rst_n) begin
            awready     <= 0;
            aw_wait_cnt <= 0;
            aw_pending  <= 0;
        end else begin
`ifdef AXI_BUG
            // BUG: awready never asserts — slave is stuck
            awready <= 0;
`else
            // CORRECT: accept write address after small delay
            if (awvalid && !awready) begin
                aw_wait_cnt <= aw_wait_cnt + 1;
                if (aw_wait_cnt >= 2) begin
                    awready     <= 1;
                    aw_pending  <= 1;
                    aw_wait_cnt <= 0;
                end
            end else begin
                awready     <= 0;
                aw_wait_cnt <= 0;
            end
`endif
        end
    end

    // ── Write Data Channel ───────────────────────────────
    always @(posedge clk) begin
        if (!rst_n) begin
            wready    <= 0;
            w_pending <= 0;
        end else begin
            if (wvalid && !wready && aw_pending) begin
                wready    <= 1;
                w_pending <= 1;
            end else begin
                wready <= 0;
            end
        end
    end

    // ── Write Response Channel ───────────────────────────
    always @(posedge clk) begin
        if (!rst_n) begin
            bvalid <= 0;
            bresp  <= 2'b00;
        end else begin
            if (w_pending && !bvalid) begin
                bvalid    <= 1;
                bresp     <= 2'b00; // OKAY
                aw_pending <= 0;
                w_pending  <= 0;
            end else if (bvalid && bready) begin
                bvalid <= 0;
            end
        end
    end

endmodule