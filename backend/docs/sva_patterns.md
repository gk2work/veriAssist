# SVA Pattern Library — VeriAssist v2.0

## Overview

This library contains curated SVA assertion patterns for common verification scenarios. Every pattern is tagged with the SVA constructs it uses and whether it is sva2sby-compatible for open-source formal verification.

Pattern format:

- Description of what the pattern checks
- Complete SystemVerilog code
- Constructs used
- sva2sby compatibility status

---

## AXI4 / AXI4-Lite Protocol Patterns

### Pattern: AXI Write Address Channel Handshake — AWVALID Stability

Once AWVALID is asserted, it must remain high until AWREADY is asserted. This is a mandatory requirement from the AMBA AXI specification. Violating this indicates a protocol error in the AXI master.

Constructs: non-overlapping implication |=>, sva2sby compatible: yes

```systemverilog
property p_awvalid_stable;
  @(posedge clk) disable iff (!rst_n)
  awvalid && !awready |=> awvalid;
endproperty

assert_awvalid_stable : assert property (p_awvalid_stable);
cover_awvalid_stable  : cover property (p_awvalid_stable);
```

### Pattern: AXI Write Address Channel — AWREADY Response Time

AWREADY must be asserted within a bounded number of cycles after AWVALID. The AMBA spec recommends but does not strictly require this, so the bound is design-specific. Typical values: 4 to 16 cycles.

Constructs: $rose, range delay ##[M:N], sva2sby compatible: yes

```systemverilog
property p_awready_response(int max_cycles = 16);
  @(posedge clk) disable iff (!rst_n)
  $rose(awvalid) |-> ##[1:max_cycles] awready;
endproperty

assert_awready_resp : assert property (p_awready_response(16));
cover_awready_resp  : cover property (p_awready_response(16));
```

### Pattern: AXI Write Data Stability

When WVALID is asserted and WREADY is not, WDATA and WSTRB must remain stable. Changing write data mid-handshake violates the AXI protocol.

Constructs: overlapping implication |->, $stable, sva2sby compatible: yes

```systemverilog
property p_wdata_stable;
  @(posedge clk) disable iff (!rst_n)
  wvalid && !wready |-> $stable(wdata) && $stable(wstrb);
endproperty

assert_wdata_stable : assert property (p_wdata_stable);
```

### Pattern: AXI Read Channel — RVALID Handshake

Once RVALID is asserted, it must remain high until RREADY is asserted. Same stability rule as write channels.

Constructs: non-overlapping implication |=>, sva2sby compatible: yes

```systemverilog
property p_rvalid_stable;
  @(posedge clk) disable iff (!rst_n)
  rvalid && !rready |=> rvalid;
endproperty

assert_rvalid_stable : assert property (p_rvalid_stable);
cover_rvalid_stable  : cover property (p_rvalid_stable);
```

### Pattern: AXI Read Data Stability

RDATA and RRESP must remain stable while RVALID is asserted and RREADY is low.

Constructs: overlapping implication |->, $stable, sva2sby compatible: yes

```systemverilog
property p_rdata_stable;
  @(posedge clk) disable iff (!rst_n)
  rvalid && !rready |-> $stable(rdata) && $stable(rresp);
endproperty

assert_rdata_stable : assert property (p_rdata_stable);
```

### Pattern: AXI Write Response — BVALID After Write

A write response (BVALID) must arrive within a bounded number of cycles after the write data handshake completes (WVALID && WREADY && WLAST).

Constructs: $rose, range delay ##[M:N], sva2sby compatible: yes

```systemverilog
property p_bresp_timing(int max_latency = 32);
  @(posedge clk) disable iff (!rst_n)
  (wvalid && wready && wlast) |-> ##[1:max_latency] bvalid;
endproperty

assert_bresp_timing : assert property (p_bresp_timing(32));
cover_bresp_timing  : cover property (p_bresp_timing(32));
```

### Pattern: AXI Parameterized Handshake (Reusable)

Generic handshake stability pattern that works for any AXI channel. Once valid is asserted, it stays high until ready. Parameterized for reuse across all channels.

Constructs: non-overlapping implication |=>, parameterized property, sva2sby compatible: yes

```systemverilog
property p_axi_handshake(valid_sig, ready_sig);
  @(posedge clk) disable iff (!rst_n)
  valid_sig && !ready_sig |=> valid_sig;
endproperty

assert_aw_handshake : assert property (p_axi_handshake(awvalid, awready));
assert_w_handshake  : assert property (p_axi_handshake(wvalid, wready));
assert_b_handshake  : assert property (p_axi_handshake(bvalid, bready));
assert_ar_handshake : assert property (p_axi_handshake(arvalid, arready));
assert_r_handshake  : assert property (p_axi_handshake(rvalid, rready));
```

---

## APB Protocol Patterns

### Pattern: APB Setup and Access Phase Timing

In APB protocol, PENABLE must be asserted exactly one cycle after PSEL goes high (setup phase to access phase transition).

Constructs: $rose, fixed delay ##1, sva2sby compatible: yes

```systemverilog
property p_apb_setup_to_access;
  @(posedge clk) disable iff (!rst_n)
  $rose(psel) |-> ##1 penable;
endproperty

assert_apb_setup : assert property (p_apb_setup_to_access);
cover_apb_setup  : cover property (p_apb_setup_to_access);
```

### Pattern: APB PREADY Response

PREADY must be asserted within a bounded number of cycles during the access phase. If the slave needs wait states, PREADY stays low, but it must eventually respond.

Constructs: range delay ##[M:N], sva2sby compatible: yes

```systemverilog
property p_apb_pready_response(int max_wait = 8);
  @(posedge clk) disable iff (!rst_n)
  (psel && penable && !pready) |-> ##[1:max_wait] pready;
endproperty

assert_apb_pready : assert property (p_apb_pready_response(8));
```

### Pattern: APB Signal Stability During Access

PADDR, PWRITE, PWDATA, and PSEL must remain stable while waiting for PREADY during the access phase.

Constructs: overlapping implication |->, $stable, sva2sby compatible: yes

```systemverilog
property p_apb_stable_during_access;
  @(posedge clk) disable iff (!rst_n)
  (psel && penable && !pready) |->
    $stable(paddr) && $stable(pwrite) && $stable(pwdata) && $stable(psel);
endproperty

assert_apb_stable : assert property (p_apb_stable_during_access);
```

---

## FIFO Patterns

### Pattern: FIFO Overflow Protection

Write enable must never be asserted when the FIFO is full. If this property fails, data will be lost.

Constructs: overlapping implication |->, sva2sby compatible: yes

```systemverilog
property p_fifo_no_overflow;
  @(posedge clk) disable iff (!rst_n)
  full |-> !wr_en;
endproperty

assert_no_overflow : assert property (p_fifo_no_overflow);
```

### Pattern: FIFO Underflow Protection

Read enable must never be asserted when the FIFO is empty. If this property fails, invalid data will be read.

Constructs: overlapping implication |->, sva2sby compatible: yes

```systemverilog
property p_fifo_no_underflow;
  @(posedge clk) disable iff (!rst_n)
  empty |-> !rd_en;
endproperty

assert_no_underflow : assert property (p_fifo_no_underflow);
```

### Pattern: FIFO Full Flag Correctness

The full flag must be asserted when the internal count equals the FIFO depth. This verifies the full flag logic is correctly implemented.

Constructs: overlapping implication |->, sva2sby compatible: yes

```systemverilog
property p_fifo_full_flag(int DEPTH);
  @(posedge clk) disable iff (!rst_n)
  (count == DEPTH) |-> full;
endproperty

assert_full_flag : assert property (p_fifo_full_flag(16));
```

### Pattern: FIFO Empty Flag Correctness

The empty flag must be asserted when the internal count equals zero.

Constructs: overlapping implication |->, sva2sby compatible: yes

```systemverilog
property p_fifo_empty_flag;
  @(posedge clk) disable iff (!rst_n)
  (count == 0) |-> empty;
endproperty

assert_empty_flag : assert property (p_fifo_empty_flag);
```

### Pattern: FIFO Data Integrity — Write Then Read

After writing data to the FIFO and then reading it back, the read data must match the written data. This assumes a single-entry FIFO scenario or uses a specific depth.

Constructs: fixed delay ##1, goto repetition [->1], sva2sby compatible: yes

```systemverilog
property p_fifo_data_integrity;
  @(posedge clk) disable iff (!rst_n)
  (wr_en && !full) |-> ##1 rd_en[->1] ##0 (rd_data == $stable(wr_data));
endproperty

cover_data_integrity : cover property (p_fifo_data_integrity);
```

---

## FSM Patterns

### Pattern: FSM No Illegal State

The FSM state register must never hold a value outside the defined state encoding. Catches bit flips, synthesis issues, or missing default cases.

Constructs: overlapping implication |->, sva2sby compatible: yes

```systemverilog
typedef enum logic [2:0] {
  IDLE  = 3'b000,
  ADDR  = 3'b001,
  DATA  = 3'b010,
  RESP  = 3'b011,
  DONE  = 3'b100
} state_t;

property p_no_illegal_state;
  @(posedge clk) disable iff (!rst_n)
  (state == IDLE) || (state == ADDR) || (state == DATA) ||
  (state == RESP) || (state == DONE);
endproperty

assert_legal_state : assert property (p_no_illegal_state);
```

### Pattern: FSM Valid Transition — No Skip

Certain state transitions should be impossible. For example, the FSM should never jump from IDLE directly to RESP, skipping the ADDR and DATA phases.

Constructs: overlapping implication |->, $changed, sva2sby compatible: yes

```systemverilog
property p_no_idle_to_resp;
  @(posedge clk) disable iff (!rst_n)
  (state == IDLE) && $changed(state) |-> (state == ADDR);
endproperty

assert_no_skip : assert property (p_no_idle_to_resp);
```

### Pattern: FSM State Reachability (Cover)

Verify that every defined state is reachable from reset. If a state is unreachable, it indicates dead logic or a design bug.

Constructs: $rose, cover property, sva2sby compatible: yes

```systemverilog
cover_reach_idle : cover property (@(posedge clk) $rose(state == IDLE));
cover_reach_addr : cover property (@(posedge clk) $rose(state == ADDR));
cover_reach_data : cover property (@(posedge clk) $rose(state == DATA));
cover_reach_resp : cover property (@(posedge clk) $rose(state == RESP));
cover_reach_done : cover property (@(posedge clk) $rose(state == DONE));
```

### Pattern: FSM Deadlock Freedom

The FSM must not remain in any non-terminal state for more than a bounded number of cycles. This detects deadlocks and livelocks.

Constructs: bounded repetition [*N], non-overlapping implication |=>, sva2sby compatible: yes

```systemverilog
property p_no_deadlock(state_t s, int max_cycles);
  @(posedge clk) disable iff (!rst_n)
  (state == s) |-> !((state == s)[*max_cycles]);
endproperty

assert_no_deadlock_addr : assert property (p_no_deadlock(ADDR, 100));
assert_no_deadlock_data : assert property (p_no_deadlock(DATA, 100));
assert_no_deadlock_resp : assert property (p_no_deadlock(RESP, 100));
```

### Pattern: FSM Return to IDLE

After reaching the DONE state, the FSM must return to IDLE within 2 clock cycles.

Constructs: range delay ##[1:2], sva2sby compatible: yes

```systemverilog
property p_done_returns_to_idle;
  @(posedge clk) disable iff (!rst_n)
  (state == DONE) |-> ##[1:2] (state == IDLE);
endproperty

assert_done_to_idle : assert property (p_done_returns_to_idle);
cover_done_to_idle  : cover property (p_done_returns_to_idle);
```

---

## General Handshake Patterns

### Pattern: Request-Acknowledge with Timeout

A request must be acknowledged within a bounded number of cycles. If the timeout expires, the design has a bug — either the responder is stuck or the request was lost.

Constructs: $rose, range delay ##[M:N], sva2sby compatible: yes

```systemverilog
property p_req_ack_timeout(int timeout = 10);
  @(posedge clk) disable iff (!rst_n)
  $rose(req) |-> ##[1:timeout] ack;
endproperty

assert_req_ack : assert property (p_req_ack_timeout(10));
cover_req_ack  : cover property (p_req_ack_timeout(10));
```

### Pattern: Mutual Exclusion

Two signals must never be asserted simultaneously. Common for arbitration, dual-port access, and bus contention checks.

Constructs: overlapping implication |->, sva2sby compatible: yes

```systemverilog
property p_mutual_exclusion;
  @(posedge clk) disable iff (!rst_n)
  !(grant_a && grant_b);
endproperty

assert_mutex : assert property (p_mutual_exclusion);
```

### Pattern: Signal Must Eventually Deassert

A signal that is asserted must eventually deassert within a bounded number of cycles. Prevents permanent assertion (stuck-at-1) bugs.

Constructs: bounded repetition [*N], sva2sby compatible: yes

```systemverilog
property p_must_deassert(int max_cycles = 50);
  @(posedge clk) disable iff (!rst_n)
  $rose(busy) |-> !((busy)[*max_cycles]);
endproperty

assert_busy_deasserts : assert property (p_must_deassert(50));
```

### Pattern: No Back-to-Back Transactions Without Gap

After a transaction completes (done asserted), there must be at least N idle cycles before the next transaction starts. Prevents pipeline hazards.

Constructs: $rose, fixed delay ##N, sva2sby compatible: yes

```systemverilog
property p_min_gap(int gap_cycles = 2);
  @(posedge clk) disable iff (!rst_n)
  $rose(done) |-> ##1 (!start)[*gap_cycles];
endproperty

assert_min_gap : assert property (p_min_gap(2));
cover_min_gap  : cover property (p_min_gap(2));
```

---

## Data Integrity Patterns

### Pattern: Data Stability While Valid

Data bus must remain stable for the entire duration that a valid signal is asserted. Common requirement for buses, FIFOs, and register interfaces.

Constructs: overlapping implication |->, $stable, throughout, sva2sby compatible: yes

```systemverilog
property p_data_stable_while_valid;
  @(posedge clk) disable iff (!rst_n)
  valid && !ready |-> $stable(data);
endproperty

assert_data_stable : assert property (p_data_stable_while_valid);
```

### Pattern: Address Must Change Between Consecutive Writes

If two consecutive write operations occur, the address must be different (no double-write to same address without a read in between).

Constructs: $rose, fixed delay ##1, $changed, sva2sby compatible: yes

```systemverilog
property p_no_double_write;
  @(posedge clk) disable iff (!rst_n)
  (wr_en) |=> wr_en |-> $changed(addr);
endproperty

assert_no_double_write : assert property (p_no_double_write);
```

### Pattern: Output Valid After Enable

After an enable signal is asserted, the output valid must be asserted within a bounded latency. Checks pipeline latency contracts.

Constructs: $rose, range delay ##[M:N], sva2sby compatible: yes

```systemverilog
property p_output_latency(int min_lat, int max_lat);
  @(posedge clk) disable iff (!rst_n)
  $rose(enable) |-> ##[min_lat:max_lat] out_valid;
endproperty

assert_latency : assert property (p_output_latency(3, 7));
cover_latency  : cover property (p_output_latency(3, 7));
```

---

## Reset Patterns

### Pattern: Reset Value Check

After reset deasserts, all outputs must hold their expected reset values on the first active clock edge.

Constructs: $rose, fixed delay ##1, sva2sby compatible: yes

```systemverilog
property p_reset_value;
  @(posedge clk)
  $rose(rst_n) |-> ##1 (data_out == '0) && (valid == 1'b0) && (state == IDLE);
endproperty

assert_reset_values : assert property (p_reset_value);
cover_reset_values  : cover property (p_reset_value);
```

### Pattern: No Activity During Reset

While reset is active, outputs must be driven to their reset values and no transactions should be initiated.

Constructs: overlapping implication |->, sva2sby compatible: yes

```systemverilog
property p_quiet_during_reset;
  @(posedge clk)
  !rst_n |-> (valid == 1'b0) && (req == 1'b0);
endproperty

assert_quiet_reset : assert property (p_quiet_during_reset);
```

---

## Formal Assumption Patterns

### Pattern: Input Constraint — Valid Encoding

Constrain the formal solver to only generate valid input encodings. Without this, the solver may find false counterexamples using illegal input combinations.

Constructs: assume property, sva2sby compatible: yes

```systemverilog
assume_valid_opcode : assume property (
  @(posedge clk) disable iff (!rst_n)
  (opcode == OP_READ) || (opcode == OP_WRITE) || (opcode == OP_NOP)
);
```

### Pattern: Input Constraint — No Simultaneous Read/Write

Constrain that read and write enables are never asserted simultaneously.

Constructs: assume property, sva2sby compatible: yes

```systemverilog
assume_no_rw_conflict : assume property (
  @(posedge clk) disable iff (!rst_n)
  !(rd_en && wr_en)
);
```

### Pattern: Input Constraint — Stable Address During Transaction

Constrain that once a transaction starts, the address remains stable until completion.

Constructs: assume property, $stable, sva2sby compatible: yes

```systemverilog
assume_addr_stable : assume property (
  @(posedge clk) disable iff (!rst_n)
  (busy && !done) |-> $stable(addr)
);
```
