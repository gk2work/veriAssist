module protocol_fsm (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       start,
    input  wire       data_valid,
    input  wire       resp_ok,
    output reg  [2:0] state
);
    localparam IDLE = 3'd0, ADDR = 3'd1, DATA = 3'd2, RESP = 3'd3, DONE = 3'd4;

    always @(posedge clk) begin
        if (!rst_n) begin
            state <= IDLE;
        end else begin
            case (state)
                IDLE: if (start)      state <= ADDR;
                ADDR:                 state <= DATA;
                DATA: if (data_valid) state <= RESP;
                RESP: if (resp_ok)    state <= DONE;
                DONE:                 state <= IDLE;
                // BUG: no default case — state 5,6,7 are reachable via corruption
            endcase
        end
    end
endmodule
