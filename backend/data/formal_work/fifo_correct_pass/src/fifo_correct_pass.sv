module sync_fifo #(
    parameter DEPTH = 8,
    parameter WIDTH = 8
)(
    input  wire             clk,
    input  wire             rst_n,
    input  wire             wr_en,
    input  wire             rd_en,
    input  wire [WIDTH-1:0] wr_data,
    output reg  [WIDTH-1:0] rd_data,
    output wire             full,
    output wire             empty,
    output reg  [$clog2(DEPTH):0] count
);
    reg [WIDTH-1:0] mem [0:DEPTH-1];
    reg [$clog2(DEPTH)-1:0] wr_ptr, rd_ptr;

    assign full  = (count == DEPTH);
    assign empty = (count == 0);

    always @(posedge clk) begin
        if (!rst_n) begin
            count  <= 0;
            wr_ptr <= 0;
            rd_ptr <= 0;
        end else begin
            // Correct: guard writes when full, reads when empty
            if (wr_en && !full) begin
                mem[wr_ptr] <= wr_data;
                wr_ptr <= wr_ptr + 1;
                count <= count + 1;
            end
            if (rd_en && !empty) begin
                rd_data <= mem[rd_ptr];
                rd_ptr <= rd_ptr + 1;
                count <= count - 1;
            end
        end
    end
endmodule
