import { useState } from "react";
import { API_BASE } from "../config/constants";

const EXAMPLE_DUTS = [
  {
    label: "FSM",
    code: `module protocol_fsm (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       start,
    input  wire       data_valid,
    input  wire       resp_ok,
    input  wire       error,
    output reg  [2:0] state
);
    localparam IDLE = 3'd0, ADDR = 3'd1, DATA = 3'd2, RESP = 3'd3, DONE = 3'd4;
    always @(posedge clk)
        if (!rst_n) state <= IDLE;
        else case (state)
            IDLE: if (start) state <= ADDR;
            ADDR: state <= DATA;
            DATA: if (data_valid) state <= RESP;
            RESP: if (resp_ok) state <= DONE;
            DONE: state <= IDLE;
            default: state <= IDLE;
        endcase
endmodule`,
  },
  {
    label: "FIFO",
    code: `module sync_fifo #(parameter DEPTH=8, parameter WIDTH=8)(
    input wire clk, input wire rst_n,
    input wire wr_en, input wire rd_en,
    input wire [WIDTH-1:0] wr_data,
    output reg [WIDTH-1:0] rd_data,
    output wire full, output wire empty
);
endmodule`,
  },
  {
    label: "AXI-Lite",
    code: `module axi_lite_slave (
    input wire clk, input wire rst_n,
    input wire awvalid, output wire awready, input wire [31:0] awaddr,
    input wire wvalid, output wire wready, input wire [31:0] wdata, input wire [3:0] wstrb,
    output wire bvalid, input wire bready, output wire [1:0] bresp,
    input wire arvalid, output wire arready, input wire [31:0] araddr,
    output wire rvalid, input wire rready, output wire [31:0] rdata, output wire [1:0] rresp
);
endmodule`,
  },
];

const PRIORITY_COLORS = {
  high: { bg: "#f8514920", color: "#f85149", border: "#f8514940" },
  medium: { bg: "#d2922220", color: "#d29922", border: "#d2922240" },
  low: { bg: "#7d859020", color: "#7d8590", border: "#7d859040" },
};

const CATEGORY_ICONS = {
  fsm_state: "\u{1F3AF}",
  fsm_transition: "\u{1F500}",
  data_boundary: "\u{1F4CA}",
  control_cross: "\u2716",
  protocol_specific: "\u{1F4E1}",
  timing: "\u23F1\uFE0F",
  toggle: "\u{1F504}",
  error_path: "\u26A0\uFE0F",
};

function PriorityBadge({ priority }) {
  const c = PRIORITY_COLORS[priority] || PRIORITY_COLORS.medium;
  return (
    <span
      style={{
        fontSize: 9,
        fontWeight: 700,
        padding: "1px 6px",
        borderRadius: 3,
        background: c.bg,
        color: c.color,
        border: `1px solid ${c.border}`,
        fontFamily: "'JetBrains Mono', monospace",
        textTransform: "uppercase",
      }}
    >
      {priority}
    </span>
  );
}

function CodeBlock({ code, title }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div>
      {title && (
        <div
          style={{
            fontSize: 10,
            color: "#7d8590",
            fontWeight: 600,
            marginBottom: 4,
            textTransform: "uppercase",
            letterSpacing: 1,
          }}
        >
          {title}
        </div>
      )}
      <div style={{ position: "relative" }}>
        <button
          onClick={copy}
          style={{
            position: "absolute",
            top: 6,
            right: 6,
            background: "#21262d",
            border: "1px solid #30363d",
            borderRadius: 4,
            color: "#7d8590",
            fontSize: 10,
            padding: "2px 8px",
            cursor: "pointer",
            zIndex: 1,
          }}
        >
          {copied ? "Copied" : "Copy"}
        </button>
        <pre
          style={{
            background: "#0d1117",
            border: "1px solid #21262d",
            borderRadius: 8,
            padding: 14,
            fontSize: 11,
            lineHeight: 1.6,
            color: "#e6edf3",
            fontFamily: "'JetBrains Mono', monospace",
            whiteSpace: "pre-wrap",
            overflowX: "auto",
            maxHeight: 400,
            overflowY: "auto",
            margin: 0,
          }}
        >
          {code}
        </pre>
      </div>
    </div>
  );
}

export default function CoveragePanel({ model }) {
  const [dutCode, setDutCode] = useState("");
  const [protocol, setProtocol] = useState("");
  const [loading, setLoading] = useState(false);
  const [analysis, setAnalysis] = useState(null);
  const [coverageModel, setCoverageModel] = useState(null);
  const [activeTab, setActiveTab] = useState("opportunities");
  const [error, setError] = useState(null);

  // ── Analyze ─────────────────────────────────────────────
  const analyzeDut = async () => {
    if (!dutCode.trim() || loading) return;
    setLoading(true);
    setError(null);
    setAnalysis(null);
    setCoverageModel(null);
    try {
      const resp = await fetch(`${API_BASE}/api/coverage/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dut_code: dutCode, protocol }),
      });
      const data = await resp.json();
      if (data.success) setAnalysis(data);
      else setError(data.error);
    } catch (err) {
      setError(err.message);
    }
    setLoading(false);
  };

  // ── Generate Coverage Model ─────────────────────────────
  const generateCoverage = async () => {
    if (!dutCode.trim() || loading) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${API_BASE}/api/coverage/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dut_code: dutCode, protocol }),
      });
      const data = await resp.json();
      if (data.success) {
        setCoverageModel(data);
        setActiveTab("covergroup");
      } else setError(data.error);
    } catch (err) {
      setError(err.message);
    }
    setLoading(false);
  };

  const loadExample = (ex) => {
    setDutCode(ex.code);
    setProtocol("");
    setAnalysis(null);
    setCoverageModel(null);
  };

  const opps = analysis?.opportunities || [];
  const fsms = analysis?.fsms || [];
  const recs = coverageModel?.recommendations || [];
  const checklist = coverageModel?.checklist || [];

  return (
    <div style={{ display: "flex", height: "100%", gap: 0 }}>
      {/* ── LEFT PANE ── */}
      <div
        style={{
          width: "clamp(280px, 30%, 380px)",
          flexShrink: 0,
          borderRight: "1px solid #21262d",
          display: "flex",
          flexDirection: "column",
          background: "#0d1117",
          overflowY: "auto",
        }}
      >
        <div
          style={{ padding: "14px 16px", borderBottom: "1px solid #21262d" }}
        >
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 2 }}>
            {"\u{1F4CA}"} Coverage Advisor
          </div>
          <div style={{ fontSize: 10, color: "#7d8590" }}>
            Analyze DUT {"\u2192"} Find Gaps {"\u2192"} Generate Coverage{" "}
            {"\u2192"} Recommend Sequences
          </div>
        </div>

        {/* DUT Code */}
        <div
          style={{ padding: "12px 16px", borderBottom: "1px solid #21262d" }}
        >
          <label style={labelStyle}>DUT Source Code</label>
          <textarea
            value={dutCode}
            onChange={(e) => setDutCode(e.target.value)}
            placeholder="Paste your DUT SystemVerilog here..."
            rows={10}
            style={{
              ...textareaStyle,
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 10,
            }}
          />
          <div
            style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 8 }}
          >
            {EXAMPLE_DUTS.map((ex, i) => (
              <button
                key={i}
                onClick={() => loadExample(ex)}
                style={chipStyle}
                onMouseEnter={(e) =>
                  (e.currentTarget.style.borderColor = "#58a6ff")
                }
                onMouseLeave={(e) =>
                  (e.currentTarget.style.borderColor = "#21262d")
                }
              >
                {ex.label}
              </button>
            ))}
          </div>
        </div>

        {/* Options */}
        <div
          style={{ padding: "12px 16px", borderBottom: "1px solid #21262d" }}
        >
          <label style={labelStyle}>Protocol Hint</label>
          <select
            value={protocol}
            onChange={(e) => setProtocol(e.target.value)}
            style={{ ...inputStyle, marginTop: 6, cursor: "pointer" }}
          >
            <option value="">auto-detect</option>
            <option value="axi">AXI</option>
            <option value="apb">APB</option>
            <option value="fifo">FIFO</option>
            <option value="spi">SPI</option>
            <option value="generic">Generic</option>
          </select>
        </div>

        {/* Stats */}
        {analysis && (
          <div
            style={{ padding: "12px 16px", borderBottom: "1px solid #21262d" }}
          >
            <label style={labelStyle}>Analysis Summary</label>
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 4,
                marginTop: 6,
              }}
            >
              <span style={tagStyle}>{analysis.protocol}</span>
              <span style={tagStyle}>
                {analysis.stats?.total_opportunities || 0} opportunities
              </span>
              <span
                style={{
                  ...tagStyle,
                  borderColor: "#f8514940",
                  color: "#f85149",
                }}
              >
                {analysis.stats?.high_priority || 0} high
              </span>
              <span
                style={{
                  ...tagStyle,
                  borderColor: "#d2922240",
                  color: "#d29922",
                }}
              >
                {analysis.stats?.medium_priority || 0} medium
              </span>
              <span style={tagStyle}>
                {analysis.stats?.low_priority || 0} low
              </span>
              {analysis.stats?.fsm_count > 0 && (
                <span
                  style={{
                    ...tagStyle,
                    borderColor: "#58a6ff40",
                    color: "#58a6ff",
                  }}
                >
                  {analysis.stats.fsm_count} FSM
                </span>
              )}
            </div>
          </div>
        )}

        {/* Buttons */}
        <div
          style={{
            padding: "12px 16px",
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          <button
            onClick={analyzeDut}
            disabled={!dutCode.trim() || loading}
            style={{
              padding: "8px 12px",
              borderRadius: 6,
              border: "none",
              background: !dutCode.trim() || loading ? "#21262d" : "#58a6ff",
              color: !dutCode.trim() || loading ? "#7d8590" : "#000",
              fontSize: 12,
              fontWeight: 600,
              cursor: !dutCode.trim() || loading ? "not-allowed" : "pointer",
              fontFamily: "inherit",
            }}
          >
            {loading && !coverageModel
              ? "\u23F3 Analyzing..."
              : "\u{1F50D} Analyze Coverage Gaps"}
          </button>

          {analysis && (
            <button
              onClick={generateCoverage}
              disabled={loading}
              style={{
                padding: "8px 12px",
                borderRadius: 6,
                border: "none",
                background: loading ? "#21262d" : "#238636",
                color: loading ? "#7d8590" : "#fff",
                fontSize: 12,
                fontWeight: 600,
                cursor: loading ? "not-allowed" : "pointer",
                fontFamily: "inherit",
              }}
            >
              {loading && coverageModel
                ? "\u23F3 Generating..."
                : "\u26A1 Generate Coverage Model"}
            </button>
          )}
        </div>
      </div>

      {/* ── RIGHT PANE ── */}
      <div
        style={{
          flex: 1,
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          background: "#010409",
          overflow: "hidden",
        }}
      >
        {/* Empty State */}
        {!analysis && !error && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              height: "100%",
              gap: 16,
              padding: 40,
            }}
          >
            <div
              style={{
                width: 56,
                height: 56,
                borderRadius: 14,
                background: "linear-gradient(135deg, #d2922218, #f8514918)",
                border: "1px solid #21262d",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 24,
              }}
            >
              {"\u{1F4CA}"}
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>
                Coverage Advisor
              </div>
              <div
                style={{
                  fontSize: 11,
                  color: "#7d8590",
                  maxWidth: 340,
                  lineHeight: 1.5,
                }}
              >
                Paste a DUT. VeriAssist detects FSMs, classifies signals,
                identifies coverage gaps, and generates a complete coverage
                model with recommended sequences.
              </div>
            </div>
          </div>
        )}

        {error && (
          <div style={{ padding: 16 }}>
            <div
              style={{
                background: "#f8514910",
                border: "1px solid #f8514930",
                borderRadius: 8,
                padding: 14,
                color: "#f85149",
                fontSize: 12,
              }}
            >
              <strong>Error:</strong> {error}
            </div>
          </div>
        )}

        {/* Tab bar */}
        {(analysis || coverageModel) && (
          <div
            style={{
              display: "flex",
              borderBottom: "1px solid #21262d",
              background: "#0d1117",
              flexShrink: 0,
            }}
          >
            {[
              {
                id: "opportunities",
                label: `Opportunities (${opps.length})`,
                show: !!analysis,
              },
              {
                id: "fsms",
                label: `FSMs (${fsms.length})`,
                show: fsms.length > 0,
              },
              { id: "covergroup", label: "Covergroup", show: !!coverageModel },
              {
                id: "sequences",
                label: `Sequences (${recs.length})`,
                show: recs.length > 0,
              },
              {
                id: "checklist",
                label: `Checklist (${checklist.length})`,
                show: checklist.length > 0,
              },
            ]
              .filter((t) => t.show)
              .map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  style={{
                    padding: "8px 16px",
                    border: "none",
                    borderBottom:
                      activeTab === tab.id
                        ? "2px solid #58a6ff"
                        : "2px solid transparent",
                    background:
                      activeTab === tab.id ? "#161b22" : "transparent",
                    color: activeTab === tab.id ? "#e6edf3" : "#7d8590",
                    fontSize: 11,
                    cursor: "pointer",
                    fontFamily: "'JetBrains Mono', monospace",
                  }}
                >
                  {tab.label}
                </button>
              ))}
          </div>
        )}

        {/* Tab Content */}
        <div style={{ flex: 1, overflowY: "auto", padding: 16 }}>
          {/* Opportunities */}
          {activeTab === "opportunities" && opps.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {opps.map((opp, i) => (
                <div
                  key={i}
                  style={{
                    background: "#0d1117",
                    border: "1px solid #21262d",
                    borderRadius: 6,
                    padding: "10px 12px",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      marginBottom: 4,
                    }}
                  >
                    <span style={{ fontSize: 13 }}>
                      {CATEGORY_ICONS[opp.category] || "\u{1F4CB}"}
                    </span>
                    <PriorityBadge priority={opp.priority} />
                    <span
                      style={{
                        fontSize: 11,
                        fontWeight: 600,
                        color: "#e6edf3",
                      }}
                    >
                      {opp.name}
                    </span>
                  </div>
                  <div
                    style={{
                      fontSize: 10,
                      color: "#7d8590",
                      lineHeight: 1.5,
                      marginBottom: 4,
                    }}
                  >
                    {opp.description}
                  </div>
                  {opp.signals?.length > 0 && (
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                      {opp.signals.map((s, j) => (
                        <span
                          key={j}
                          style={{
                            fontSize: 9,
                            padding: "1px 4px",
                            borderRadius: 2,
                            background: "#161b22",
                            border: "1px solid #21262d",
                            color: "#58a6ff",
                            fontFamily: "'JetBrains Mono', monospace",
                          }}
                        >
                          {s}
                        </span>
                      ))}
                    </div>
                  )}
                  {opp.coverpoint_hint && (
                    <details style={{ marginTop: 4 }}>
                      <summary
                        style={{
                          fontSize: 9,
                          color: "#7d8590",
                          cursor: "pointer",
                        }}
                      >
                        Coverpoint hint
                      </summary>
                      <pre
                        style={{
                          marginTop: 4,
                          background: "#161b22",
                          borderRadius: 4,
                          padding: 6,
                          fontSize: 9,
                          color: "#e6edf3",
                          fontFamily: "'JetBrains Mono', monospace",
                          whiteSpace: "pre-wrap",
                        }}
                      >
                        {opp.coverpoint_hint}
                      </pre>
                    </details>
                  )}
                  {opp.sequence_hint && (
                    <div
                      style={{
                        fontSize: 9,
                        color: "#3fb950",
                        marginTop: 4,
                        fontStyle: "italic",
                      }}
                    >
                      {"\u{1F4A1}"} {opp.sequence_hint}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* FSMs */}
          {activeTab === "fsms" &&
            fsms.map((fsm, i) => (
              <div key={i} style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>
                  FSM: {fsm.state_reg} ({fsm.states.length} states,{" "}
                  {fsm.transitions.length} transitions)
                  {fsm.has_default && (
                    <span
                      style={{ fontSize: 9, color: "#3fb950", marginLeft: 8 }}
                    >
                      {"\u2713"} has default
                    </span>
                  )}
                  {!fsm.has_default && (
                    <span
                      style={{ fontSize: 9, color: "#f85149", marginLeft: 8 }}
                    >
                      {"\u2717"} no default
                    </span>
                  )}
                </div>
                <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                  <div>
                    <div
                      style={{
                        fontSize: 10,
                        color: "#7d8590",
                        fontWeight: 600,
                        marginBottom: 4,
                      }}
                    >
                      States
                    </div>
                    {fsm.states.map((s, j) => (
                      <div
                        key={j}
                        style={{
                          fontSize: 10,
                          fontFamily: "'JetBrains Mono', monospace",
                          color: "#e6edf3",
                          marginBottom: 1,
                        }}
                      >
                        {s.name} = {s.value}{" "}
                        {s.name === fsm.reset_state ? "\u{1F504} reset" : ""}
                      </div>
                    ))}
                  </div>
                  <div>
                    <div
                      style={{
                        fontSize: 10,
                        color: "#7d8590",
                        fontWeight: 600,
                        marginBottom: 4,
                      }}
                    >
                      Transitions
                    </div>
                    {fsm.transitions.map((t, j) => (
                      <div
                        key={j}
                        style={{
                          fontSize: 10,
                          fontFamily: "'JetBrains Mono', monospace",
                          color: "#e6edf3",
                          marginBottom: 1,
                        }}
                      >
                        {t.from_state} {"\u2192"} {t.to_state}{" "}
                        {t.condition ? `(${t.condition})` : ""}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ))}

          {/* Covergroup */}
          {activeTab === "covergroup" && coverageModel && (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <span style={tagStyle}>
                  {coverageModel.total_coverpoints} coverpoints
                </span>
                <span style={tagStyle}>
                  {coverageModel.total_crosses} crosses
                </span>
              </div>
              <CodeBlock
                code={coverageModel.covergroup_code}
                title="Covergroup"
              />
              <CodeBlock
                code={coverageModel.subscriber_code}
                title="UVM Subscriber"
              />
            </div>
          )}

          {/* Sequences */}
          {activeTab === "sequences" &&
            recs.map((rec, i) => (
              <div
                key={i}
                style={{
                  marginBottom: 16,
                  background: "#0d1117",
                  border: "1px solid #21262d",
                  borderRadius: 6,
                  padding: "10px 12px",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    marginBottom: 4,
                  }}
                >
                  <PriorityBadge priority={rec.priority} />
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 600,
                      color: "#e6edf3",
                      fontFamily: "'JetBrains Mono', monospace",
                    }}
                  >
                    {rec.name}
                  </span>
                </div>
                <div
                  style={{ fontSize: 10, color: "#7d8590", marginBottom: 4 }}
                >
                  {rec.description}
                </div>
                {rec.target_coverage?.length > 0 && (
                  <div
                    style={{ fontSize: 9, color: "#58a6ff", marginBottom: 4 }}
                  >
                    Targets: {rec.target_coverage.join(", ")}
                  </div>
                )}
                {rec.sequence_code && <CodeBlock code={rec.sequence_code} />}
              </div>
            ))}

          {/* Checklist */}
          {activeTab === "checklist" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {checklist.map((item, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "6px 10px",
                    background: "#0d1117",
                    border: "1px solid #21262d",
                    borderRadius: 4,
                  }}
                >
                  <span style={{ fontSize: 13, opacity: 0.4 }}>{"\u2610"}</span>
                  <PriorityBadge priority={item.priority} />
                  <span style={{ fontSize: 10, color: "#e6edf3", flex: 1 }}>
                    {item.item}
                  </span>
                  <span
                    style={{
                      fontSize: 9,
                      color: "#7d8590",
                      fontFamily: "'JetBrains Mono', monospace",
                    }}
                  >
                    {item.category}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────
const labelStyle = {
  fontSize: 10,
  color: "#7d8590",
  fontWeight: 600,
  textTransform: "uppercase",
  letterSpacing: 1,
};
const inputStyle = {
  width: "100%",
  background: "#161b22",
  border: "1px solid #21262d",
  borderRadius: 4,
  color: "#e6edf3",
  padding: "4px 8px",
  fontSize: 11,
  fontFamily: "'JetBrains Mono', monospace",
  outline: "none",
};
const textareaStyle = {
  width: "100%",
  marginTop: 6,
  background: "#161b22",
  border: "1px solid #21262d",
  borderRadius: 6,
  color: "#e6edf3",
  padding: "8px 10px",
  fontSize: 12,
  fontFamily: "inherit",
  resize: "vertical",
  outline: "none",
  minHeight: 150,
};
const chipStyle = {
  background: "#161b22",
  border: "1px solid #21262d",
  borderRadius: 4,
  color: "#7d8590",
  fontSize: 9,
  padding: "2px 6px",
  cursor: "pointer",
  fontFamily: "'JetBrains Mono', monospace",
  transition: "border-color .15s",
};
const tagStyle = {
  fontSize: 9,
  padding: "1px 6px",
  borderRadius: 3,
  background: "#161b22",
  border: "1px solid #21262d",
  color: "#7d8590",
  fontFamily: "'JetBrains Mono', monospace",
};
