module axi_slave (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        awvalid,
    output reg         awready
);
    // BUG: awready never asserts (stuck at 0)
    always @(posedge clk) begin
        if (!rst_n)
            awready <= 0;
        else
            awready <= 0;  // BUG: should eventually go high
    end
endmodule
