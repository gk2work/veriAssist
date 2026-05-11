`ifdef FORMAL
module formal_wrapper (
    input wire clk,
    input wire rst_n
);

    (* anyseq *) wire awvalid;
    wire awready;

    axi_slave u_dut (
        .clk(clk),
        .rst_n(rst_n),
        .awvalid(awvalid),
        .awready(awready)
    );

    axi_formal_checker u_monitor (
        .clk(clk),
        .rst_n(rst_n),
        .awvalid(awvalid),
        .awready(awready)
    );

endmodule
`endif