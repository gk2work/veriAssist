#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from app.services.sva_lowering import SVALoweringEngine

e = SVALoweringEngine()
print("Test 1:", repr(e._clean_expr('( (empty_out))')))
print("Test 2:", repr(e._clean_expr('(!rd_en_in) ')))
print("Test 3:", repr(e._clean_expr('(1)')))
print("Test 4:", repr(e._clean_expr('( (`full_out))')))

# Also quick-test the full lowering of an assume with overlapping
from app.services.sva_lowering import lower_sva_to_rtl
code = """module test_chk();
    default clocking cb @(posedge clk); endclocking
    default disable iff (!rst_n);
    property p1; (empty_out) |-> (!rd_en_in); endproperty
    test1: assume property (p1);
endmodule"""

result = lower_sva_to_rtl(code)
# Print lines around the assume
for i, line in enumerate(result.split('\n'), 1):
    if 'assume' in line or 'if' in line.lower() and 'rst' not in line:
        print(f"  L{i}: {line}")