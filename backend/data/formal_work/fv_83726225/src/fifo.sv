// Synchronous FIFO — depth 8, width 8-bit
// Reset: active-low reset_n
module fifo #(
    parameter DATA_W = 8,
    parameter DEPTH  = 8
) (
    input  logic                clk,
    input  logic                reset_n,
    input  logic                wr_en,
    input  logic                rd_en,
    input  logic [DATA_W-1:0]   wr_data,
    output logic [DATA_W-1:0]   rd_data,
    output logic                full,
    output logic                empty
);

    localparam PTR_W = $clog2(DEPTH);

    logic [DATA_W-1:0] mem [0:DEPTH-1];
    logic [PTR_W:0]    wr_ptr;
    logic [PTR_W:0]    rd_ptr;

    // Full / empty derived from MSB of pointers
    assign full  = (wr_ptr[PTR_W] != rd_ptr[PTR_W]) &&
                   (wr_ptr[PTR_W-1:0] == rd_ptr[PTR_W-1:0]);
    assign empty = (wr_ptr == rd_ptr);

    assign rd_data = mem[rd_ptr[PTR_W-1:0]];

    always_ff @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            wr_ptr <= '0;
            rd_ptr <= '0;
        end else begin
            if (wr_en && !full) begin
                mem[wr_ptr[PTR_W-1:0]] <= wr_data;
                wr_ptr <= wr_ptr + 1'b1;
            end
            if (rd_en && !empty) begin
                rd_ptr <= rd_ptr + 1'b1;
            end
        end
    end

endmodule
