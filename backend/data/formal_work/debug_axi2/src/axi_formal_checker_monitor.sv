`ifdef FORMAL
module axi_formal_checker (
    input wire clk,
    input wire rst_n,
    input wire awvalid,
    input wire awready
);

    // --- assert_test: assert property (p_test) ---
    // Original SVA: awready |-> awvalid
    always @(posedge clk) begin
        if (!(!rst_n)) begin
            if (awready && !(awvalid))
                assert_test: assert(0);
        end
    end

endmodule
`endif // FORMAL