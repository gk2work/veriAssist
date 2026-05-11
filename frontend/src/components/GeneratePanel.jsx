import { useState } from "react";
import { API_BASE } from "../config/constants";

const EXAMPLE_DUTS = [
  {
    label: "FIFO",
    code: `module sync_fifo #(parameter DEPTH = 8, parameter WIDTH = 8)(
    input  wire             clk,
    input  wire             rst_n,
    input  wire             wr_en,
    input  wire             rd_en,
    input  wire [WIDTH-1:0] wr_data,
    output reg  [WIDTH-1:0] rd_data,
    output wire             full,
    output wire             empty
);
endmodule`,
  },
  {
    label: "AXI-Lite",
    code: `module axi_lite_slave (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        awvalid,
    output wire        awready,
    input  wire [31:0] awaddr,
    input  wire        wvalid,
    output wire        wready,
    input  wire [31:0] wdata,
    input  wire [3:0]  wstrb,
    output wire        bvalid,
    input  wire        bready,
    output wire [1:0]  bresp,
    input  wire        arvalid,
    output wire        arready,
    input  wire [31:0] araddr,
    output wire        rvalid,
    input  wire        rready,
    output wire [31:0] rdata,
    output wire [1:0]  rresp
);
endmodule`,
  },
  {
    label: "APB",
    code: `module apb_slave (
    input  wire        pclk,
    input  wire        presetn,
    input  wire        psel,
    input  wire        penable,
    input  wire        pwrite,
    input  wire [31:0] paddr,
    input  wire [31:0] pwdata,
    output wire        pready,
    output wire [31:0] prdata,
    output wire        pslverr
);
endmodule`,
  },
  {
    label: "SPI",
    code: `module spi_master (
    input  wire       clk,
    input  wire       rst_n,
    output wire       sclk,
    output wire       mosi,
    input  wire       miso,
    output wire       cs_n,
    input  wire       start,
    input  wire [7:0] tx_data,
    output reg  [7:0] rx_data,
    output wire       busy
);
endmodule`,
  },
];

const COMPONENT_ICONS = {
  package: "\u{1F4E6}",
  interface: "\u{1F50C}",
  transaction: "\u{1F4E8}",
  config: "\u2699\uFE0F",
  sequencer: "\u{1F500}",
  driver: "\u{1F3CE}\uFE0F",
  monitor: "\u{1F4E1}",
  coverage: "\u{1F4CA}",
  scoreboard: "\u{1F3AF}",
  agent: "\u{1F916}",
  seq_lib: "\u{1F4DA}",
  env: "\u{1F3D7}\uFE0F",
  test: "\u{1F9EA}",
};

function CodeBlock({ code }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
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
          maxHeight: "calc(100vh - 300px)",
          overflowY: "auto",
          margin: 0,
        }}
      >
        {code}
      </pre>
    </div>
  );
}

export default function GeneratePanel({ model }) {
  const [dutCode, setDutCode] = useState("");
  const [name, setName] = useState("");
  const [protocol, setProtocol] = useState("");
  const [goals, setGoals] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [interfacePreview, setInterfacePreview] = useState(null);
  const [activeTab, setActiveTab] = useState(0);
  const [error, setError] = useState(null);

  // ── Parse Interface (preview) ───────────────────────────
  const parseInterface = async () => {
    if (!dutCode.trim()) return;
    try {
      const resp = await fetch(`${API_BASE}/api/uvm/parse-interface`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dut_code: dutCode,
          module_name: name,
          protocol,
        }),
      });
      const data = await resp.json();
      if (data.success) setInterfacePreview(data);
      else setError(data.error);
    } catch (err) {
      setError(err.message);
    }
  };

  // ── Generate UVM Testbench ──────────────────────────────
  const generate = async () => {
    if (!dutCode.trim() || loading) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setActiveTab(0);
    try {
      const resp = await fetch(`${API_BASE}/api/uvm/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dut_code: dutCode, name, protocol, goals }),
      });
      const data = await resp.json();
      if (data.success) setResult(data);
      else setError(data.error);
    } catch (err) {
      setError(err.message);
    }
    setLoading(false);
  };

  // ── Download All ────────────────────────────────────────
  const downloadAll = () => {
    if (!result?.files) return;
    result.files.forEach((f) => {
      const blob = new Blob([f.content], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = f.filename;
      a.click();
      URL.revokeObjectURL(url);
    });
  };

  const loadExample = (ex) => {
    setDutCode(ex.code);
    setName("");
    setProtocol("");
    setInterfacePreview(null);
    setResult(null);
  };
  const iface = result?.interface || interfacePreview?.interface;
  const files = result?.files || [];

  return (
    <div style={{ display: "flex", height: "100%", gap: 0 }}>
      {/* ── LEFT PANE ── */}
      <div
        style={{
          width: 380,
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
            {"\u26A1"} UVM Generator
          </div>
          <div style={{ fontSize: 10, color: "#7d8590" }}>
            Paste DUT {"\u2192"} Parse Interface {"\u2192"} Generate Full
            Testbench
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
            placeholder="Paste your DUT SystemVerilog module here...&#10;&#10;module my_dut (&#10;    input wire clk,&#10;    input wire rst_n,&#10;    ...&#10;);&#10;endmodule"
            rows={8}
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
          <label style={labelStyle}>Options</label>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 8,
              marginTop: 6,
            }}
          >
            <div>
              <div style={sublabelStyle}>Component Name</div>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="auto-detect"
                style={inputStyle}
              />
            </div>
            <div>
              <div style={sublabelStyle}>Protocol Hint</div>
              <select
                value={protocol}
                onChange={(e) => setProtocol(e.target.value)}
                style={{ ...inputStyle, cursor: "pointer" }}
              >
                <option value="">auto-detect</option>
                <option value="axi">AXI</option>
                <option value="axi_lite">AXI-Lite</option>
                <option value="apb">APB</option>
                <option value="spi">SPI</option>
                <option value="uart">UART</option>
                <option value="fifo">FIFO</option>
                <option value="wishbone">Wishbone</option>
                <option value="generic">Generic</option>
              </select>
            </div>
          </div>
          <div style={{ marginTop: 8 }}>
            <div style={sublabelStyle}>Verification Goals (optional)</div>
            <input
              value={goals}
              onChange={(e) => setGoals(e.target.value)}
              placeholder="e.g., test all opcodes, check overflow..."
              style={inputStyle}
            />
          </div>
        </div>

        {/* Interface Preview */}
        {iface && (
          <div
            style={{ padding: "12px 16px", borderBottom: "1px solid #21262d" }}
          >
            <label style={labelStyle}>Detected Interface</label>
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 4,
                marginTop: 6,
              }}
            >
              <span style={tagStyle}>{iface.protocol}</span>
              <span style={tagStyle}>{iface.signal_count} signals</span>
              <span style={tagStyle}>
                {iface.input_count} in / {iface.output_count} out
              </span>
              {iface.has_handshake && (
                <span
                  style={{
                    ...tagStyle,
                    borderColor: "#23863640",
                    color: "#3fb950",
                  }}
                >
                  handshake
                </span>
              )}
              <span style={tagStyle}>clk: {iface.clock}</span>
              <span style={tagStyle}>rst: {iface.reset}</span>
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
            onClick={parseInterface}
            disabled={!dutCode.trim()}
            style={secondaryBtnStyle}
          >
            {"\u{1F50D}"} Preview Interface
          </button>
          <button
            onClick={generate}
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
            {loading ? "\u23F3 Generating..." : "\u26A1 Generate UVM Testbench"}
          </button>
          {result && (
            <button
              onClick={downloadAll}
              style={{
                ...secondaryBtnStyle,
                borderColor: "#23863640",
                color: "#3fb950",
              }}
            >
              {"\u{1F4E5}"} Download All Files ({files.length})
            </button>
          )}
        </div>
      </div>

      {/* ── RIGHT PANE ── */}
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          background: "#010409",
        }}
      >
        {/* Empty State */}
        {!result && !error && (
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
                background: "linear-gradient(135deg, #58a6ff18, #3fb95018)",
                border: "1px solid #21262d",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 24,
              }}
            >
              {"\u26A1"}
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>
                UVM Testbench Generator
              </div>
              <div
                style={{
                  fontSize: 11,
                  color: "#7d8590",
                  maxWidth: 340,
                  lineHeight: 1.5,
                }}
              >
                Paste a DUT module. VeriAssist auto-detects the protocol, parses
                signals, and generates a complete UVM testbench — transaction,
                driver, monitor, scoreboard, coverage, sequences, and test.
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

        {/* Generated Files */}
        {result && (
          <div
            style={{ display: "flex", flexDirection: "column", height: "100%" }}
          >
            {/* Summary Bar */}
            <div
              style={{
                padding: "10px 16px",
                borderBottom: "1px solid #21262d",
                background: "#0d1117",
                display: "flex",
                alignItems: "center",
                gap: 12,
                flexShrink: 0,
              }}
            >
              <span style={{ fontSize: 12, fontWeight: 600 }}>
                {result.name}
              </span>
              <span
                style={{
                  ...tagStyle,
                  background: "#23863620",
                  borderColor: "#23863640",
                  color: "#3fb950",
                }}
              >
                {result.protocol}
              </span>
              <span
                style={{
                  fontSize: 10,
                  color: "#7d8590",
                  fontFamily: "'JetBrains Mono', monospace",
                }}
              >
                {result.file_count} files {"\u2022"} {result.total_lines} lines{" "}
                {"\u2022"} {result.generation_time}s
              </span>
            </div>

            {/* Tab Bar */}
            <div
              style={{
                display: "flex",
                overflowX: "auto",
                borderBottom: "1px solid #21262d",
                background: "#0d1117",
                flexShrink: 0,
              }}
            >
              {files.map((f, i) => {
                const icon = COMPONENT_ICONS[f.component_type] || "\u{1F4C4}";
                const isActive = activeTab === i;
                return (
                  <button
                    key={i}
                    onClick={() => setActiveTab(i)}
                    style={{
                      padding: "6px 12px",
                      border: "none",
                      borderBottom: isActive
                        ? "2px solid #58a6ff"
                        : "2px solid transparent",
                      background: isActive ? "#161b22" : "transparent",
                      color: isActive ? "#e6edf3" : "#7d8590",
                      fontSize: 10,
                      fontFamily: "'JetBrains Mono', monospace",
                      cursor: "pointer",
                      whiteSpace: "nowrap",
                      display: "flex",
                      alignItems: "center",
                      gap: 4,
                      transition: "all 0.15s",
                    }}
                    onMouseEnter={(e) => {
                      if (!isActive) e.currentTarget.style.color = "#e6edf3";
                    }}
                    onMouseLeave={(e) => {
                      if (!isActive) e.currentTarget.style.color = "#7d8590";
                    }}
                  >
                    <span style={{ fontSize: 11 }}>{icon}</span>
                    {f.component_type}
                  </button>
                );
              })}
            </div>

            {/* Active File Content */}
            {files[activeTab] && (
              <div
                style={{
                  flex: 1,
                  display: "flex",
                  flexDirection: "column",
                  overflow: "hidden",
                }}
              >
                {/* File Header */}
                <div
                  style={{
                    padding: "8px 16px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    borderBottom: "1px solid #21262d",
                    background: "#0d1117",
                    flexShrink: 0,
                  }}
                >
                  <div>
                    <span
                      style={{
                        fontSize: 12,
                        fontWeight: 600,
                        fontFamily: "'JetBrains Mono', monospace",
                        color: "#e6edf3",
                      }}
                    >
                      {files[activeTab].filename}
                    </span>
                    <span
                      style={{ fontSize: 10, color: "#7d8590", marginLeft: 8 }}
                    >
                      {files[activeTab].lines} lines {"\u2022"}{" "}
                      {files[activeTab].description}
                    </span>
                  </div>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(files[activeTab].content);
                    }}
                    style={{
                      background: "#21262d",
                      border: "1px solid #30363d",
                      borderRadius: 4,
                      color: "#7d8590",
                      fontSize: 10,
                      padding: "2px 8px",
                      cursor: "pointer",
                    }}
                  >
                    Copy
                  </button>
                </div>

                {/* Code */}
                <div
                  style={{
                    flex: 1,
                    overflow: "auto",
                    padding: "0 16px 16px 16px",
                  }}
                >
                  <pre
                    style={{
                      background: "#0d1117",
                      padding: 14,
                      fontSize: 11,
                      lineHeight: 1.6,
                      color: "#e6edf3",
                      fontFamily: "'JetBrains Mono', monospace",
                      whiteSpace: "pre-wrap",
                      margin: 0,
                    }}
                  >
                    {files[activeTab].content}
                  </pre>
                </div>
              </div>
            )}
          </div>
        )}
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
const sublabelStyle = { fontSize: 9, color: "#7d8590", marginBottom: 2 };
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
  minHeight: 120,
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
const secondaryBtnStyle = {
  padding: "6px 10px",
  borderRadius: 6,
  background: "#161b22",
  border: "1px solid #21262d",
  color: "#7d8590",
  fontSize: 11,
  cursor: "pointer",
  fontFamily: "'JetBrains Mono', monospace",
};
