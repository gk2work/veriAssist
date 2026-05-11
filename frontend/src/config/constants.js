export const API_BASE = "http://localhost:8000";

export const MODES = [
  { id: "chat", label: "Chat", icon: "\u{1F4AC}", desc: "General VLSI Q&A" },
  {
    id: "docs",
    label: "Docs",
    icon: "\u{1F4D6}",
    desc: "Documentation lookup",
  },
  {
    id: "generate",
    label: "Generate",
    icon: "\u26A1",
    desc: "UVM code generation",
  },
  { id: "sva", label: "SVA", icon: "\u{1F512}", desc: "Assertion writing" },
  {
    id: "formal",
    label: "Formal",
    icon: "\u{1F9EA}",
    desc: "sva2sby formal proof",
  },
  { id: "debug", label: "Debug", icon: "\u{1F41B}", desc: "Error analysis" },
  { id: "fv", label: "Formal Verification", icon: "\u{1F52C}", desc: "File-based formal verification" },
];

export const QUICK_PROMPTS = {
  chat: [
    "What is the difference between uvm_component and uvm_object?",
    "Explain UVM factory override mechanism",
    "How does TLM analysis port work in UVM?",
    "When should I use virtual sequences?",
  ],
  docs: [
    "What are the arguments to uvm_config_db::set?",
    "List all UVM phase methods in execution order",
    "What SVA constructs does sva2sby support?",
    "How to configure SymbiYosys .sby file?",
  ],
  generate: [
    "Generate a UVM driver for AXI4-Lite slave interface",
    "Create a UVM scoreboard with in-order checking",
    "Build a functional coverage model for APB transactions",
    "Write a UVM register model for a simple SPI controller",
  ],
  sva: [
    "ACK must arrive within 5 cycles of REQ going high",
    "Data bus must be stable while VALID is asserted",
    "Write AXI write channel handshake assertions",
    "No two consecutive writes without a read in between",
  ],
  formal: [
    "Formally verify: AWVALID stays high until AWREADY",
    "Prove FIFO never overflows (wr_en while full is impossible)",
    "Verify FSM never enters ILLEGAL state from any input",
    "Check: response always arrives within 8 cycles of request",
  ],
  debug: [
    "UVM_FATAL: no set_sequencer call on driver",
    "Phase objection raised but never dropped in run_phase",
    "Null object access in scoreboard write() method",
    "Formal property FAIL: p_resp_timeout at cycle 15",
  ],
};

// ── Formal Mode Configuration ────────────────────────────

export const FORMAL_CONFIG = {
  defaultClock: "clk",
  defaultReset: "rst_n",
  defaultSolver: "boolector",
  defaultBmcDepth: 20,
  solvers: [
    {
      id: "boolector",
      label: "Boolector",
      desc: "Fast BMC solver (recommended)",
    },
    { id: "yices", label: "Yices 2", desc: "SMT solver, good for k-induction" },
    { id: "z3", label: "Z3", desc: "General-purpose SMT solver (fallback)" },
  ],
  protocols: [
    { id: "axi", label: "AXI4 / AXI4-Lite" },
    { id: "ahb", label: "AHB" },
    { id: "apb", label: "APB" },
    { id: "spi", label: "SPI" },
    { id: "i2c", label: "I2C" },
    { id: "uart", label: "UART" },
    { id: "fifo", label: "FIFO" },
    { id: "fsm", label: "FSM / State Machine" },
  ],
  bmcDepthRange: { min: 5, max: 100, step: 5 },
};

// ── SVA Construct Reference (for UI tooltips) ────────────

export const SVA_CONSTRUCTS = {
  supported: [
    { name: "|->", desc: "Overlapping implication" },
    { name: "|=>", desc: "Non-overlapping implication" },
    { name: "##N", desc: "Fixed delay (N cycles)" },
    { name: "##[M:N]", desc: "Range delay (M to N cycles)" },
    { name: "[*N]", desc: "Bounded consecutive repetition" },
    { name: "[->N]", desc: "Goto repetition (N occurrences)" },
    { name: "[=N]", desc: "Non-consecutive repetition" },
    { name: "$rose", desc: "Rising edge detection" },
    { name: "$fell", desc: "Falling edge detection" },
    { name: "$stable", desc: "Value unchanged from previous cycle" },
    { name: "$changed", desc: "Value changed from previous cycle" },
    { name: "throughout", desc: "Condition holds during entire sequence" },
    { name: "disable iff", desc: "Reset/disable condition" },
  ],
  banned: [
    { name: "$past", fix: "Use $stable or $changed" },
    { name: "first_match", fix: "Use bounded repetition" },
    { name: "intersect", fix: "Use separate properties" },
    { name: "within", fix: "Use throughout" },
    { name: "[*] / [+]", fix: "Use bounded [*N] or [*M:N]" },
    { name: "$onehot", fix: "Implement as explicit logic" },
  ],
};
