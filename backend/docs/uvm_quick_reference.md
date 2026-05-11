# UVM 1.2 Quick Reference — VeriAssist v2.0

## Overview

This reference covers the most commonly used UVM 1.2 classes, methods, macros, and patterns. It is designed for working verification engineers who need fast, accurate lookups during testbench development.

UVM version: 1.2 (IEEE 1800.2-2017 aligned)

---

## UVM Class Hierarchy

### Core Base Classes

The UVM class hierarchy has two fundamental branches:

**uvm_object** — Base class for all UVM data objects. Does NOT participate in the UVM component hierarchy. Does NOT have phases. Used for transactions, sequences, configuration objects, and any data container.

**uvm_component** — Base class for all UVM structural components. Participates in the UVM hierarchy (has parent/child relationships). Has phases (build, connect, run, etc.). Used for drivers, monitors, agents, environments, scoreboards, and tests.

Key distinction: uvm_object instances are transient (created and destroyed during simulation). uvm_component instances are persistent (created during build_phase and exist for the entire simulation).

### Component Hierarchy

```
uvm_object
  ├── uvm_transaction
  │     └── uvm_sequence_item          // Base for all transactions
  ├── uvm_sequence                      // Base for all sequences
  └── uvm_reg_field / uvm_reg / ...    // Register model classes

uvm_component
  ├── uvm_driver                        // Drives transactions to DUT
  ├── uvm_monitor                       // Observes DUT interface
  ├── uvm_sequencer                     // Routes sequences to driver
  ├── uvm_agent                         // Groups driver+monitor+sequencer
  ├── uvm_env                           // Top-level environment
  ├── uvm_test                          // Test entry point
  ├── uvm_scoreboard                    // Checking logic
  └── uvm_subscriber                   // Coverage collection
```

---

## Registration Macros

Every UVM class MUST be registered with the factory using the appropriate macro.

### For uvm_component subclasses

```systemverilog
class my_driver extends uvm_driver #(my_transaction);
  `uvm_component_utils(my_driver)

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction
endclass
```

### For uvm_object subclasses

```systemverilog
class my_transaction extends uvm_sequence_item;
  `uvm_object_utils(my_transaction)

  function new(string name = "my_transaction");
    super.new(name);
  endfunction
endclass
```

### Field Macros (for transactions)

Register fields for automatic print, compare, copy, pack, unpack:

```systemverilog
class my_transaction extends uvm_sequence_item;
  rand bit [31:0] addr;
  rand bit [31:0] data;
  rand bit        wr_rd;

  `uvm_object_utils_begin(my_transaction)
    `uvm_field_int(addr, UVM_ALL_ON)
    `uvm_field_int(data, UVM_ALL_ON)
    `uvm_field_int(wr_rd, UVM_ALL_ON)
  `uvm_object_utils_end

  function new(string name = "my_transaction");
    super.new(name);
  endfunction
endclass
```

Field macro flags: UVM_ALL_ON, UVM_DEFAULT, UVM_NOPRINT, UVM_NOCOMPARE, UVM_NOCOPY, UVM_NOPACK, UVM_READONLY.

Note: Some teams prefer implementing do_print, do_compare, do_copy manually instead of field macros for better performance and control.

---

## UVM Phases

Phases execute in this order. All components at the same level execute the same phase before moving to the next.

### Build-Time Phases (top-down)

**build_phase** — Create child components, set configuration. Executes top-down (parent before child). This is where you call uvm_config_db::get and type_id::create.

```systemverilog
function void build_phase(uvm_phase phase);
  super.build_phase(phase);
  driver = my_driver::type_id::create("driver", this);
  monitor = my_monitor::type_id::create("monitor", this);
endfunction
```

**connect_phase** — Connect TLM ports, analysis ports, virtual interfaces. Executes bottom-up (child before parent).

```systemverilog
function void connect_phase(uvm_phase phase);
  super.connect_phase(phase);
  driver.seq_item_port.connect(sequencer.seq_item_export);
  monitor.analysis_port.connect(scoreboard.analysis_imp);
endfunction
```

### Run-Time Phases (parallel)

**run_phase** — Main simulation phase. All run_phase tasks execute in parallel across all components. Use raise_objection and drop_objection to control simulation end.

```systemverilog
task run_phase(uvm_phase phase);
  phase.raise_objection(this);
  // ... run test sequences ...
  phase.drop_objection(this);
endtask
```

### Cleanup Phases (bottom-up)

**extract_phase** — Extract results from scoreboards and coverage.
**check_phase** — Check for errors, compare expected vs actual.
**report_phase** — Print final reports, summaries, pass/fail status.
**final_phase** — Last phase, used for cleanup.

---

## uvm_config_db

The configuration database is used to pass configuration objects, virtual interfaces, and parameters between components without hard-coded hierarchical paths.

### Setting a value (typically in test or environment)

```systemverilog
// Set a virtual interface
uvm_config_db #(virtual my_interface)::set(
  this,           // context: who is setting
  "env.agent*",   // inst_name: target path (wildcards allowed)
  "vif",          // field_name: lookup key
  my_vif          // value: what to store
);

// Set a configuration object
uvm_config_db #(my_config)::set(
  this, "env.agent*", "config", my_cfg
);

// Set a simple integer
uvm_config_db #(int)::set(
  this, "env.agent*", "is_active", UVM_ACTIVE
);
```

### Getting a value (typically in build_phase)

```systemverilog
function void build_phase(uvm_phase phase);
  super.build_phase(phase);

  // Get virtual interface — fatal if not found
  if (!uvm_config_db #(virtual my_interface)::get(
    this, "", "vif", vif))
  begin
    `uvm_fatal("NOVIF", "Virtual interface not set for this agent")
  end

  // Get configuration object
  if (!uvm_config_db #(my_config)::get(
    this, "", "config", cfg))
  begin
    `uvm_fatal("NOCFG", "Configuration object not found")
  end
endfunction
```

### Key Rules

- The type parameter must match exactly between set and get.
- Use wildcards in inst_name for broad configuration: "env.agent\*" matches env.agent, env.agent0, env.agent_rx.
- Always call get in build_phase, never in new.
- The context (first argument) determines the hierarchical scope for name resolution.

---

## TLM Communication

### Analysis Ports (one-to-many broadcast)

The most common TLM pattern in UVM. Monitor broadcasts transactions to scoreboard and coverage.

#### In the Monitor (sender)

```systemverilog
class my_monitor extends uvm_monitor;
  uvm_analysis_port #(my_transaction) analysis_port;

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    analysis_port = new("analysis_port", this);
  endfunction

  task run_phase(uvm_phase phase);
    forever begin
      my_transaction txn;
      // ... observe interface, create txn ...
      analysis_port.write(txn);  // broadcast to all connected
    end
  endtask
endclass
```

#### In the Scoreboard (receiver)

```systemverilog
class my_scoreboard extends uvm_scoreboard;
  `uvm_component_utils(my_scoreboard)

  uvm_analysis_imp #(my_transaction, my_scoreboard) analysis_imp;

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    analysis_imp = new("analysis_imp", this);
  endfunction

  // This function is called automatically when monitor writes
  function void write(my_transaction txn);
    // ... compare, check, score ...
    `uvm_info("SCB", $sformatf("Received: addr=%0h data=%0h", txn.addr, txn.data), UVM_MEDIUM)
  endfunction
endclass
```

#### Connection (in environment connect_phase)

```systemverilog
monitor.analysis_port.connect(scoreboard.analysis_imp);
```

### Analysis FIFO (buffered)

When the receiver needs to process at its own pace (not in the write callback):

```systemverilog
class my_scoreboard extends uvm_scoreboard;
  uvm_tlm_analysis_fifo #(my_transaction) expected_fifo;
  uvm_tlm_analysis_fifo #(my_transaction) actual_fifo;

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    expected_fifo = new("expected_fifo", this);
    actual_fifo = new("actual_fifo", this);
  endfunction

  task run_phase(uvm_phase phase);
    my_transaction exp_txn, act_txn;
    forever begin
      expected_fifo.get(exp_txn);  // blocks until available
      actual_fifo.get(act_txn);
      if (!exp_txn.compare(act_txn))
        `uvm_error("SCB", "Mismatch!")
    end
  endtask
endclass
```

### Sequencer-Driver Communication

The driver pulls transactions from the sequencer via a built-in TLM port:

```systemverilog
class my_driver extends uvm_driver #(my_transaction);
  task run_phase(uvm_phase phase);
    forever begin
      my_transaction txn;
      seq_item_port.get_next_item(txn);  // blocks until sequence provides item
      // ... drive txn on interface ...
      seq_item_port.item_done();          // tell sequencer we're done
    end
  endtask
endclass
```

---

## Factory

The UVM factory enables object creation with runtime type overrides.

### Creating objects (always use factory)

```systemverilog
// CORRECT — factory creation
my_driver drv = my_driver::type_id::create("drv", this);
my_transaction txn = my_transaction::type_id::create("txn");

// WRONG — direct construction bypasses factory
my_driver drv = new("drv", this);  // DO NOT DO THIS
```

### Type Override (global)

Replace all instances of one type with another:

```systemverilog
// In test build_phase
function void build_phase(uvm_phase phase);
  super.build_phase(phase);
  // Replace base driver with extended version everywhere
  my_driver::type_id::set_type_override(my_extended_driver::get_type());
endfunction
```

### Instance Override (specific)

Replace only a specific instance:

```systemverilog
// Replace driver only in agent0
my_driver::type_id::set_inst_override(
  my_special_driver::get_type(),
  "env.agent0.driver"
);
```

---

## Sequences

### Basic Sequence Structure

```systemverilog
class my_sequence extends uvm_sequence #(my_transaction);
  `uvm_object_utils(my_sequence)

  function new(string name = "my_sequence");
    super.new(name);
  endfunction

  task body();
    my_transaction txn;

    repeat(10) begin
      txn = my_transaction::type_id::create("txn");
      start_item(txn);       // request sequencer arbitration
      assert(txn.randomize() with {
        addr inside {[32'h0000 : 32'hFFFF]};
      });
      finish_item(txn);      // send to driver, wait for item_done
    end
  endtask
endclass
```

### Starting a Sequence (from test)

```systemverilog
task run_phase(uvm_phase phase);
  my_sequence seq;
  phase.raise_objection(this);

  seq = my_sequence::type_id::create("seq");
  seq.start(env.agent.sequencer);  // blocks until body() completes

  phase.drop_objection(this);
endtask
```

### Virtual Sequence (coordinates multiple agents)

```systemverilog
class my_virtual_sequence extends uvm_sequence;
  `uvm_object_utils(my_virtual_sequence)
  `uvm_declare_p_sequencer(my_virtual_sequencer)

  task body();
    my_write_seq wr_seq = my_write_seq::type_id::create("wr_seq");
    my_read_seq  rd_seq = my_read_seq::type_id::create("rd_seq");

    fork
      wr_seq.start(p_sequencer.write_sqr);
      rd_seq.start(p_sequencer.read_sqr);
    join
  endtask
endclass
```

---

## Agent Structure

### Complete Agent Template

```systemverilog
class my_agent extends uvm_agent;
  `uvm_component_utils(my_agent)

  my_driver    driver;
  my_monitor   monitor;
  my_sequencer sequencer;
  my_config    cfg;

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);

    // Get config
    if (!uvm_config_db #(my_config)::get(this, "", "config", cfg))
      `uvm_fatal("NOCFG", "Agent config not found")

    // Monitor always created
    monitor = my_monitor::type_id::create("monitor", this);

    // Driver and sequencer only in ACTIVE mode
    if (cfg.is_active == UVM_ACTIVE) begin
      driver = my_driver::type_id::create("driver", this);
      sequencer = my_sequencer::type_id::create("sequencer", this);
    end
  endfunction

  function void connect_phase(uvm_phase phase);
    super.connect_phase(phase);
    if (cfg.is_active == UVM_ACTIVE) begin
      driver.seq_item_port.connect(sequencer.seq_item_export);
    end
  endfunction
endclass
```

---

## Messaging

### Message Macros

```systemverilog
`uvm_info("TAG", "Informational message", UVM_MEDIUM)
`uvm_warning("TAG", "Warning: something unexpected")
`uvm_error("TAG", "Error: check failed")
`uvm_fatal("TAG", "Fatal: cannot continue")
```

### Verbosity Levels

UVM_NONE (0) — always printed
UVM_LOW (100) — important info
UVM_MEDIUM (200) — standard info (default threshold)
UVM_HIGH (300) — detailed info
UVM_FULL (400) — very detailed
UVM_DEBUG (500) — debug only

### Setting Verbosity

```systemverilog
// In test (programmatic)
env.agent.driver.set_report_verbosity_level(UVM_HIGH);

// Command line
+UVM_VERBOSITY=UVM_HIGH
+uvm_set_verbosity=*driver*,_ALL_,UVM_HIGH
```

---

## Objections

Objections control when the simulation ends. The run_phase continues as long as any component has a raised objection.

### Correct Pattern

```systemverilog
task run_phase(uvm_phase phase);
  phase.raise_objection(this, "Starting test sequence");
  // ... run sequences ...
  phase.drop_objection(this, "Test sequence complete");
endtask
```

### Common Mistakes

- Raising objection but never dropping it — simulation hangs forever.
- Dropping objection before sequences complete — simulation ends prematurely.
- Raising objection in a component that doesn't start sequences — unnecessary.
- Not calling raise_objection at all — simulation ends immediately at run_phase.

### Timeout

Set simulation timeout to catch hung tests:

```systemverilog
// In test build_phase
uvm_top.set_timeout(10ms);

// Command line
+UVM_TIMEOUT=10000000  // in simulation time units
```

---

## Functional Coverage

### Covergroup in Monitor

```systemverilog
class my_monitor extends uvm_monitor;
  my_transaction txn;

  covergroup cg_transaction;
    cp_addr: coverpoint txn.addr {
      bins low  = {[0:32'hFF]};
      bins mid  = {[32'h100:32'hFFFF]};
      bins high = {[32'h10000:$]};
    }
    cp_wr_rd: coverpoint txn.wr_rd {
      bins write = {1};
      bins read  = {0};
    }
    cx_addr_wr: cross cp_addr, cp_wr_rd;
  endgroup

  function new(string name, uvm_component parent);
    super.new(name, parent);
    cg_transaction = new();
  endfunction

  task run_phase(uvm_phase phase);
    forever begin
      // ... collect txn from interface ...
      cg_transaction.sample();
    end
  endtask
endclass
```

### Coverage using uvm_subscriber

```systemverilog
class my_coverage extends uvm_subscriber #(my_transaction);
  `uvm_component_utils(my_coverage)

  covergroup cg with function sample(my_transaction txn);
    // coverpoints here
  endgroup

  function new(string name, uvm_component parent);
    super.new(name, parent);
    cg = new();
  endfunction

  function void write(my_transaction t);
    cg.sample(t);
  endfunction
endclass
```

---

## UVM Register Model (RAL)

### Register Definition

```systemverilog
class my_reg extends uvm_reg;
  `uvm_object_utils(my_reg)

  rand uvm_reg_field data;
  rand uvm_reg_field status;

  function new(string name = "my_reg");
    super.new(name, 32, UVM_NO_COVERAGE);
  endfunction

  virtual function void build();
    data = uvm_reg_field::type_id::create("data");
    data.configure(this, 16, 0, "RW", 0, 16'h0, 1, 1, 1);
    // configure(parent, size, lsb_pos, access, volatile, reset, has_reset, is_rand, individually_accessible)

    status = uvm_reg_field::type_id::create("status");
    status.configure(this, 8, 16, "RO", 0, 8'h0, 1, 0, 1);
  endfunction
endclass
```

### Register Block

```systemverilog
class my_reg_block extends uvm_reg_block;
  `uvm_object_utils(my_reg_block)

  rand my_reg ctrl_reg;
  rand my_reg status_reg;
  uvm_reg_map default_map;

  function new(string name = "my_reg_block");
    super.new(name, UVM_NO_COVERAGE);
  endfunction

  virtual function void build();
    ctrl_reg = my_reg::type_id::create("ctrl_reg");
    ctrl_reg.configure(this);
    ctrl_reg.build();

    status_reg = my_reg::type_id::create("status_reg");
    status_reg.configure(this);
    status_reg.build();

    default_map = create_map("default_map", 0, 4, UVM_LITTLE_ENDIAN);
    default_map.add_reg(ctrl_reg, 32'h0000);
    default_map.add_reg(status_reg, 32'h0004);
  endfunction
endclass
```

### Register Access in Sequences

```systemverilog
task body();
  uvm_status_e status;
  uvm_reg_data_t rdata;

  // Write
  reg_model.ctrl_reg.write(status, 32'hDEADBEEF);

  // Read
  reg_model.status_reg.read(status, rdata);

  // Mirror check (read and compare with mirror)
  reg_model.ctrl_reg.mirror(status, UVM_CHECK);

  // Peek (backdoor read without bus transaction)
  reg_model.status_reg.peek(status, rdata);

  // Poke (backdoor write without bus transaction)
  reg_model.ctrl_reg.poke(status, 32'h12345678);
endtask
```

---

## Common Patterns

### Environment Template

```systemverilog
class my_env extends uvm_env;
  `uvm_component_utils(my_env)

  my_agent      agent;
  my_scoreboard scoreboard;
  my_coverage   coverage;

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    agent      = my_agent::type_id::create("agent", this);
    scoreboard = my_scoreboard::type_id::create("scoreboard", this);
    coverage   = my_coverage::type_id::create("coverage", this);
  endfunction

  function void connect_phase(uvm_phase phase);
    super.connect_phase(phase);
    agent.monitor.analysis_port.connect(scoreboard.analysis_imp);
    agent.monitor.analysis_port.connect(coverage.analysis_export);
  endfunction
endclass
```

### Test Template

```systemverilog
class my_test extends uvm_test;
  `uvm_component_utils(my_test)

  my_env env;
  my_config cfg;

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);

    // Create and configure
    cfg = my_config::type_id::create("cfg");
    cfg.is_active = UVM_ACTIVE;

    uvm_config_db #(my_config)::set(this, "env.agent*", "config", cfg);
    env = my_env::type_id::create("env", this);
  endfunction

  task run_phase(uvm_phase phase);
    my_sequence seq;
    phase.raise_objection(this);

    seq = my_sequence::type_id::create("seq");
    seq.start(env.agent.sequencer);

    phase.drop_objection(this);
  endtask
endclass
```

---

## Command Line Arguments

```
+UVM_TESTNAME=my_test            # Select test to run
+UVM_VERBOSITY=UVM_HIGH          # Set verbosity level
+UVM_TIMEOUT=10000000            # Set simulation timeout
+UVM_CONFIG_DB_TRACE             # Trace all config_db set/get calls
+UVM_OBJECTION_TRACE             # Trace all objection raise/drop
+UVM_PHASE_TRACE                 # Trace phase transitions
+uvm_set_severity=*,_ALL_,UVM_ERROR,UVM_FATAL  # Promote errors to fatal
```
