# sva2sby — SVA Construct Reference

## Overview

sva2sby is a source-to-source SVA lowering CLI engine that bridges the gap between concurrent SystemVerilog Assertions (SVA) and the OSS-CAD Suite's SymbiYosys formal verification flow. It takes SVA properties and automatically lowers them into synthesizable monitor logic that SymbiYosys can verify — no commercial Verific frontend required.

## How sva2sby Works

sva2sby performs source-to-source transformation in four stages:

### Stage 1: Parse

Reads .sv files and identifies SVA property, sequence, and assertion blocks using context-aware parsing.

### Stage 2: Analyze

Builds a dependency graph of named sequences and properties, resolves parameters, identifies clock domains and reset conditions.

### Stage 3: Lower

For each concurrent SVA construct, generates an equivalent synthesizable RTL monitor module:

- Implications become conditional checkers
- Delays become shift registers or counters
- Repetitions become finite state machines with counters
- System functions become edge-detection logic

### Stage 4: Stage

Creates a clean SymbiYosys (.sby) project directory with the original DUT files and the generated monitor files under `ifdef FORMAL — without modifying the user's source tree.

---

## Supported SVA Constructs

### Implication Operators

#### Overlapping Implication |->

The overlapping implication operator checks the consequent starting in the same cycle that the antecedent completes.

```systemverilog
property p_overlap;
  req |-> gnt;
endproperty
```

sva2sby lowering: generates a combinational check — when `req` is true, `gnt` must also be true in the same cycle.

#### Non-Overlapping Implication |=>

The non-overlapping implication operator checks the consequent starting one cycle after the antecedent completes. Equivalent to `|-> ##1`.

```systemverilog
property p_non_overlap;
  req |=> ack;
endproperty
```

sva2sby lowering: generates a 1-cycle delayed check using a register. When `req` is true, a flag is set, and `ack` is checked on the next rising clock edge.

---

### Delay Operators

#### Fixed Delay ##N

Specifies an exact number of clock cycles between two events.

```systemverilog
property p_fixed_delay;
  req |-> ##3 ack;
endproperty
```

sva2sby lowering: generates an N-stage shift register pipeline. When the antecedent matches, a token enters the pipeline and arrives N cycles later to trigger the consequent check.

#### Range Delay ##[M:N]

Specifies a window of clock cycles within which the consequent must occur.

```systemverilog
property p_range_delay;
  req |-> ##[1:5] ack;
endproperty
```

sva2sby lowering: generates a counter that starts counting when the antecedent matches. The consequent is checked in every cycle from cycle M to cycle N. If `ack` is true in any cycle within the window, the property passes.

#### Zero Delay ##0

Equivalent to same-cycle check (useful in sequences).

```systemverilog
sequence s_same_cycle;
  a ##0 b;
endsequence
```

sva2sby lowering: simple combinational AND — both `a` and `b` must be true simultaneously.

---

### Repetition Operators

#### Bounded Consecutive Repetition [*N]

The signal must be true for exactly N consecutive clock cycles.

```systemverilog
property p_bounded_rep;
  req |-> data_valid[*4];
endproperty
```

sva2sby lowering: generates a counter that counts consecutive cycles where `data_valid` is true. If the count reaches N, the repetition matches. Counter resets if `data_valid` goes low before reaching N.

#### Bounded Range Repetition [*M:N]

The signal must be true for at least M and at most N consecutive clock cycles.

```systemverilog
property p_range_rep;
  req |-> data_valid[*2:5];
endproperty
```

sva2sby lowering: similar to bounded repetition but with a window — the counter checks if the consecutive count falls within [M, N].

#### Goto Repetition [->N]

The signal must be true exactly N times, not necessarily consecutively. After the Nth occurrence, the match completes on that exact cycle.

```systemverilog
property p_goto_rep;
  start |-> ack[->3];
endproperty
```

sva2sby lowering: generates a counter that increments each cycle where `ack` is true (regardless of gaps). When the count reaches N, the repetition matches on that cycle.

#### Non-Consecutive Repetition [=N]

Similar to goto repetition — the signal must be true exactly N times, not necessarily consecutively. However, unlike goto, the match does not require the sequence to end on the Nth occurrence.

```systemverilog
property p_nonconsec_rep;
  start |-> ack[=3];
endproperty
```

sva2sby lowering: similar to goto but without the end-cycle constraint. The counter reaches N, and the match is registered but the overall sequence can continue.

---

### System Functions

#### $rose(signal)

True when the signal transitions from 0 to 1 (rising edge).

```systemverilog
property p_rose;
  $rose(req) |-> ##[1:5] ack;
endproperty
```

sva2sby lowering: posedge detection logic — `signal && !past_signal` where `past_signal` is a 1-cycle delayed version stored in a register.

#### $fell(signal)

True when the signal transitions from 1 to 0 (falling edge).

```systemverilog
property p_fell;
  $fell(busy) |-> ready;
endproperty
```

sva2sby lowering: negedge detection logic — `!signal && past_signal`.

#### $stable(signal)

True when the signal has the same value as the previous cycle.

```systemverilog
property p_stable;
  valid |-> $stable(data);
endproperty
```

sva2sby lowering: equality check — `signal == past_signal`.

#### $changed(signal)

True when the signal has a different value from the previous cycle.

```systemverilog
property p_changed;
  write_en |=> $changed(addr);
endproperty
```

sva2sby lowering: inequality check — `signal != past_signal`.

---

### Reset and Clock

#### disable iff

Disables the property when the specified condition is true. Used for asynchronous reset handling.

```systemverilog
property p_with_reset;
  @(posedge clk) disable iff (!rst_n)
  req |-> ##[1:3] ack;
endproperty
```

sva2sby lowering: wraps the entire monitor logic in a reset guard. When the disable condition is active, all internal state (counters, shift registers, flags) is reset, and no assertions fire.

#### default clocking

Specifies the clock domain for all properties in the module.

```systemverilog
default clocking cb @(posedge clk);
endclocking
```

sva2sby lowering: all generated monitor logic is clocked on this edge. The clock specification is extracted and applied to all always_ff blocks in the lowered RTL.

#### default disable iff

Specifies the default reset condition for all properties in the module.

```systemverilog
default disable iff (!rst_n);
```

sva2sby lowering: applied as the reset guard to every monitor in the module.

---

### Sequences

#### Named Sequences

Reusable sequence definitions that can be referenced in properties.

```systemverilog
sequence s_handshake;
  valid ##[1:3] ready;
endsequence

property p_uses_seq;
  $rose(start) |-> s_handshake;
endproperty
```

sva2sby lowering: the sequence is inlined into each property that references it. The lowering logic resolves the sequence definition and expands it at each call site.

#### Sequence with throughout

The `throughout` operator ensures a condition holds true during the entire duration of a sequence.

```systemverilog
property p_throughout;
  $rose(req) |-> (en throughout (##[1:5] ack));
endproperty
```

sva2sby lowering: the throughout condition is checked on every cycle while the sequence is being evaluated. If the condition fails during any cycle of the sequence, the property fails.

---

### Properties

#### Named Properties

Reusable property definitions.

```systemverilog
property p_response(sig_req, sig_ack, max_delay);
  $rose(sig_req) |-> ##[1:max_delay] sig_ack;
endproperty
```

#### Parameterized Properties

Properties with parameters for reusability across different signal sets.

```systemverilog
property p_handshake(valid_sig, ready_sig);
  valid_sig && !ready_sig |=> valid_sig;
endproperty

assert_aw : assert property (p_handshake(awvalid, awready));
assert_w  : assert property (p_handshake(wvalid, wready));
```

sva2sby lowering: parameters are substituted at elaboration time. Each assertion instance creates a separate monitor with the actual signal names.

---

### Assertion Types

#### assert property

Checks that a property always holds. A violation generates a formal counterexample.

```systemverilog
assert_name : assert property (p_my_property);
```

sva2sby lowering: the monitor output drives a synthesizable assertion under `ifdef FORMAL that SymbiYosys checks using SAT/SMT solvers.

#### assume property

Constrains the formal solver's input space. The solver will only explore traces where the assumption holds. Use for input protocol constraints.

```systemverilog
assume_valid_input : assume property (
  @(posedge clk) disable iff (!rst_n)
  $rose(req) |-> !busy
);
```

sva2sby lowering: similar to assert but generates an assumption constraint instead. SymbiYosys treats assumptions as axioms — it will never generate a trace that violates them.

#### cover property

Checks that a property CAN be satisfied. SymbiYosys finds a trace that makes the property true (reachability analysis).

```systemverilog
cover_handshake : cover property (
  @(posedge clk) disable iff (!rst_n)
  $rose(req) ##[1:5] ack
);
```

sva2sby lowering: generates a cover target. SymbiYosys in cover mode attempts to find an input sequence that satisfies the property.

---

### Bind Statement

The bind statement attaches a checker module to a DUT without modifying the DUT source code.

```systemverilog
bind my_dut my_checker u_checker (
  .clk(clk),
  .rst_n(rst_n),
  .req(req),
  .ack(ack)
);
```

Or using implicit port connection:

```systemverilog
bind my_dut my_checker u_checker (.*);
```

sva2sby lowering: the bind statement is rewritten for the sby project staging. sva2sby ensures the checker module is included in the SymbiYosys project and properly connected to the DUT during formal elaboration.

---

## UNSUPPORTED Constructs

The following SVA constructs are NOT supported by sva2sby. Using them will cause the lowering to fail. Use the suggested alternatives instead.

### $past(signal)

NOT supported. Use `$stable(signal)` or `$changed(signal)` instead.

```systemverilog
// WRONG — will fail in sva2sby
property p_wrong;
  data == $past(data);
endproperty

// CORRECT — use $stable instead
property p_correct;
  $stable(data);
endproperty
```

### first_match

NOT supported. Use bounded repetition with explicit bounds instead.

### intersect

NOT supported. Express the intersection as separate properties.

### within

NOT supported. Use `throughout` for continuous condition checks, or express as separate temporal logic.

### Unbounded Repetition [*] and [+]

NOT supported. Always use bounded repetition with explicit upper bounds.

```systemverilog
// WRONG — will fail in sva2sby
property p_wrong;
  req[*] ##1 ack;
endproperty

// CORRECT — use bounded repetition
property p_correct;
  req[*1:100] ##1 ack;
endproperty
```

### $countones, $onehot, $onehot0

NOT supported. Implement as explicit combinational logic in the checker module.

```systemverilog
// WRONG — will fail in sva2sby
property p_wrong;
  $onehot(state);
endproperty

// CORRECT — implement as explicit logic
logic is_onehot;
assign is_onehot = (state != '0) && ((state & (state - 1)) == '0);

property p_correct;
  is_onehot;
endproperty
```

### Local Variables in Sequences

NOT supported. Use module-level signals or checker ports instead.

### Recursive Properties

NOT supported. Express recursive patterns using bounded repetition or explicit FSM logic.

---

## CLI Usage

### Basic Lowering

```bash
sva2sby lower my_assertions.sv --dut my_design.sv --output-dir formal_work/
```

### With Clock and Reset Override

```bash
sva2sby lower my_assertions.sv --dut my_design.sv --clk sys_clk --rst sys_rst_n
```

### Running the Full Flow (Lower + Prove)

```bash
sva2sby lower my_assertions.sv --dut my_design.sv --output-dir formal_work/
cd formal_work/
sby -f project.sby
```

### SymbiYosys Result Interpretation

- **PASS**: Property holds for all reachable states up to the BMC depth
- **FAIL**: Property violation found — counterexample VCD generated in engine_0/trace.vcd
- **UNKNOWN**: Solver ran out of time or memory — increase timeout or reduce BMC depth
- **ERROR**: Synthesis or elaboration error — check Yosys output for details

---

## Best Practices for sva2sby-Compatible SVA

1. Always use `default clocking` and `default disable iff` at the module level
2. Use named properties and sequences — never anonymous inline assertions
3. Include both `assert` and `cover` versions of each property
4. Use parameterized properties for protocol-level reusability
5. Keep BMC depth reasonable — start with 20 cycles, increase if needed
6. Use `assume property` to constrain inputs, `assert property` to check outputs
7. Test each property individually before combining into a large formal suite
8. Use `bind` statements to keep formal code separate from RTL
