// ═══════════════════════════════════════════════════════════════
// VeriAssist v2.0 — Example DUT: Protocol FSM (5 States)
//
// Two variants controlled by `define:
//   Default (no define)  → Correct: has default case → IDLE
//   `define FSM_BUG      → Buggy: no default, states 5-7 reachable
//
// Formal properties to verify:
//   1. No illegal state: state always in {IDLE,ADDR,DATA,RESP,DONE}
//   2. No deadlock: FSM doesn't stay in any state > 100 cycles
//   3. Return to IDLE: after DONE, returns to IDLE within 2 cycles
//   4. State reachability: all 5 states are reachable (cover)
//   5. Valid transitions: no skip from IDLE directly to RESP
// ═══════════════════════════════════════════════════════════════

module protocol_fsm (
    input  wire       clk,
    input  wire       rst_n,

    // Control inputs
    input  wire       start,
    input  wire       data_valid,
    input  wire       resp_ok,
    input  wire       error,

    // State output
    output reg  [2:0] state,

    // Status outputs
    output wire       busy,
    output wire       done_pulse,
    output reg        error_flag
);

    // State encoding
    localparam IDLE = 3'd0;
    localparam ADDR = 3'd1;
    localparam DATA = 3'd2;
    localparam RESP = 3'd3;
    localparam DONE = 3'd4;

    reg [2:0] state_prev;
    assign busy       = (state != IDLE);
    assign done_pulse = (state == DONE) && (state_prev != DONE);

    // Track previous state for done_pulse
    always @(posedge clk) begin
        if (!rst_n)
            state_prev <= IDLE;
        else
            state_prev <= state;
    end

    // ── FSM Next-State Logic ─────────────────────────────
    always @(posedge clk) begin
        if (!rst_n) begin
            state      <= IDLE;
            error_flag <= 0;
        end else begin
            case (state)
                IDLE: begin
                    error_flag <= 0;
                    if (start)
                        state <= ADDR;
                end

                ADDR: begin
                    state <= DATA;
                end

                DATA: begin
                    if (error) begin
                        state      <= IDLE;
                        error_flag <= 1;
                    end else if (data_valid) begin
                        state <= RESP;
                    end
                end

                RESP: begin
                    if (error) begin
                        state      <= IDLE;
                        error_flag <= 1;
                    end else if (resp_ok) begin
                        state <= DONE;
                    end
                end

                DONE: begin
                    state <= IDLE;
                end

`ifdef FSM_BUG
                // BUG: no default case
                // If state is corrupted to 5, 6, or 7 (e.g., by SEU or
                // synthesis tool placing don't-care), FSM is stuck forever
                // in an illegal state with no recovery path.
`else
                // CORRECT: default returns to safe state
                default: begin
                    state      <= IDLE;
                    error_flag <= 1;
                end
`endif
            endcase
        end
    end

endmodule