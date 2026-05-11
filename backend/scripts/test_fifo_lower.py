#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from app.services.sva_lowering import lower_sva_to_rtl

fifo_sva = """
module fifo_sva ();
    property fifo_empty_no_read;
        ( (empty_out)|->(!rd_en_in) );
    endproperty
    test1: assume property(@(posedge clk_in) disable iff (!rst_n_in) fifo_empty_no_read);
endmodule
"""

result = lower_sva_to_rtl(fifo_sva)
for i, line in enumerate(result.split('\n'), 1):
    print(f"{i:3d}: {line}")