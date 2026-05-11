
module axi_slave (
    input wire clk, input wire rst_n,
    input wire awvalid, output reg awready
);
    reg [3:0] counter;
    always @(posedge clk) begin
        if (!rst_n) begin awready <= 0; counter <= 0; end
        else begin
            if (awvalid && !awready) begin
                counter <= counter + 1;
                if (counter >= 3) awready <= 1;
            end else begin awready <= 0; counter <= 0; end
        end
    end
endmodule
