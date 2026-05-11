module fifo (
    input clk,
    input rst,
    input wen,
    input ren,
    input [7:0] wdata,
    output reg [7:0] rdata
);

    reg [7:0] mem [0:15];
    reg [3:0] wptr, rptr;
    reg [4:0] count;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            wptr <= 0;
            rptr <= 0;
            count <= 0;
        end else begin
            if (wen && count < 16) begin
                mem[wptr] <= wdata;
                wptr <= wptr + 1;
                count <= count + 1;
            end

            if (ren && count > 0) begin
                rdata <= mem[rptr];
                rptr <= rptr + 1;
                count <= count - 1;
            end
        end
    end

endmodule