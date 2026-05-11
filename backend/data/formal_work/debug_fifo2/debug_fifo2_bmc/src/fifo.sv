
module sync_fifo #(parameter DEPTH = 8, parameter WIDTH = 8)(
    input wire clk, input wire rst_n,
    input wire wr_en, input wire [WIDTH-1:0] wr_data,
    input wire rd_en, output reg [WIDTH-1:0] rd_data,
    output wire full, output wire empty,
    output reg [$clog2(DEPTH):0] count
);
    reg [WIDTH-1:0] mem [0:DEPTH-1];
    reg [$clog2(DEPTH)-1:0] wr_ptr, rd_ptr;
    assign full = (count == DEPTH);
    assign empty = (count == 0);
    always @(posedge clk) begin
        if (!rst_n) begin wr_ptr <= 0; end
        else if (wr_en) begin mem[wr_ptr] <= wr_data; wr_ptr <= wr_ptr + 1; end
    end
    always @(posedge clk) begin
        if (!rst_n) begin rd_ptr <= 0; rd_data <= 0; end
        else if (rd_en && !empty) begin rd_data <= mem[rd_ptr]; rd_ptr <= rd_ptr + 1; end
    end
    always @(posedge clk) begin
        if (!rst_n) count <= 0;
        else case ({wr_en, rd_en && !empty})
            2'b10: count <= count + 1;
            2'b01: count <= count - 1;
            default: count <= count;
        endcase
    end
endmodule
