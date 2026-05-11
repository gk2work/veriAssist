import { useState } from "react";
import { API_BASE } from "../config/constants";

const EXAMPLE_PROMPTS = [
  {
    label: "AXI handshake",
    desc: "AWVALID must stay high until AWREADY is asserted",
    protocol: "axi",
  },
  {
    label: "FIFO overflow",
    desc: "Write enable must never be asserted when FIFO is full",
    protocol: "fifo",
  },
  {
    label: "Response timeout",
    desc: "ACK must arrive within 10 cycles after REQ goes high",
    protocol: null,
  },
  {
    label: "Data stability",
    desc: "Data bus must remain stable while valid is high",
    protocol: null,
  },
  {
    label: "FSM illegal state",
    desc: "FSM must never enter a state outside IDLE, ADDR, DATA, RESP, DONE",
    protocol: null,
  },
];

const CLASSIFICATION_COLORS = {
  DESIGN_BUG: { bg: "#f8514920", color: "#f85149", label: "Design Bug" },
  PROPERTY_ISSUE: {
    bg: "#d2922220",
    color: "#d29922",
    label: "Property Issue",
  },
  CONSTRAINT_MISSING: {
    bg: "#58a6ff20",
    color: "#58a6ff",
    label: "Missing Constraint",
  },
  RESET_ISSUE: { bg: "#bc8cff20", color: "#bc8cff", label: "Reset Issue" },
  UNKNOWN: { bg: "#21262d", color: "#7d8590", label: "Unknown" },
};

function Badge({ ok, label }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        fontSize: 10,
        fontWeight: 600,
        padding: "2px 8px",
        borderRadius: 4,
        fontFamily: "'JetBrains Mono', monospace",
        background: ok ? "#23863620" : "#f8514920",
        color: ok ? "#3fb950" : "#f85149",
        border: `1px solid ${ok ? "#23863640" : "#f8514940"}`,
      }}
    >
      {ok ? "\u2713" : "\u2717"} {label}
    </span>
  );
}

function FormalBadge({ status }) {
  const colors = {
    PASS: { bg: "#23863630", color: "#3fb950", border: "#23863650" },
    FAIL: { bg: "#f8514930", color: "#f85149", border: "#f8514950" },
    TIMEOUT: { bg: "#d2922230", color: "#d29922", border: "#d2922250" },
    ERROR: { bg: "#f8514920", color: "#f85149", border: "#f8514940" },
  };
  const c = colors[status] || colors.ERROR;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        fontSize: 13,
        fontWeight: 700,
        padding: "4px 14px",
        borderRadius: 6,
        fontFamily: "'JetBrains Mono', monospace",
        background: c.bg,
        color: c.color,
        border: `2px solid ${c.border}`,
      }}
    >
      {status === "PASS" ? "\u2713" : status === "FAIL" ? "\u2717" : "\u26A0"}{" "}
      {status}
    </span>
  );
}

function StatBadge({ label, value }) {
  return (
    <span
      style={{
        fontSize: 9,
        padding: "2px 6px",
        borderRadius: 3,
        background: "#161b22",
        border: "1px solid #21262d",
        color: "#7d8590",
        fontFamily: "'JetBrains Mono', monospace",
      }}
    >
      {label}: {value}
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

function ClassificationBadge({ classification }) {
  const c =
    CLASSIFICATION_COLORS[classification] || CLASSIFICATION_COLORS.UNKNOWN;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        fontSize: 11,
        fontWeight: 700,
        padding: "3px 10px",
        borderRadius: 5,
        fontFamily: "'JetBrains Mono', monospace",
        background: c.bg,
        color: c.color,
        border: `1px solid ${c.color}30`,
      }}
    >
      {c.label}
    </span>
  );
}

export default function FormalPanel({ model }) {
  // Pipeline mode: "english" = English→SVA→Lower→Prove, "sva" = Paste SVA→Lower→Prove
  const [pipeline, setPipeline] = useState("english");

  const [description, setDescription] = useState("");
  const [svaCode, setSvaCode] = useState(""); // for direct SVA pipeline
  const [clock, setClock] = useState("clk");
  const [reset, setReset] = useState("rst_n");
  const [protocol, setProtocol] = useState("");
  const [dutModule, setDutModule] = useState("");
  const [solver, setSolver] = useState("");
  const [bmcDepth, setBmcDepth] = useState(20);
  const [dutCode, setDutCode] = useState("");

  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState("");
  const [svaResult, setSvaResult] = useState(null);
  const [formalResult, setFormalResult] = useState(null);
  const [debugAnalysis, setDebugAnalysis] = useState(null);
  const [loweredRtl, setLoweredRtl] = useState(null);
  const [rerunResult, setRerunResult] = useState(null);
  const [error, setError] = useState(null);

  const resetResults = () => {
    setSvaResult(null);
    setFormalResult(null);
    setDebugAnalysis(null);
    setLoweredRtl(null);
    setRerunResult(null);
    setError(null);
  };

  // Get the active SVA code (from generation or direct paste)
  const activeSvaCode =
    pipeline === "english" ? svaResult?.sva_code || "" : svaCode;

  // ── Generate SVA (Pipeline A only) ──────────────────────
  const generateSVA = async () => {
    if (!description.trim() || loading) return;
    setLoading(true);
    setStep("generating");
    resetResults();
    try {
      const resp = await fetch(`${API_BASE}/api/sva/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          description,
          clock,
          reset,
          protocol: protocol || null,
          dut_module: dutModule || null,
          mode: "formal",
          model: model || undefined,
          stream: false,
          auto_retry: true,
        }),
      });
      const data = await resp.json();
      if (data.detail) setError(data.detail);
      else setSvaResult(data);
    } catch (err) {
      setError(err.message);
    }
    setStep("");
    setLoading(false);
  };

  // ── Run Formal ──────────────────────────────────────────
  const runFormal = async () => {
    if (!activeSvaCode || loading) return;
    setLoading(true);
    setStep("proving");
    setFormalResult(null);
    setDebugAnalysis(null);
    setRerunResult(null);
    try {
      const resp = await fetch(`${API_BASE}/api/formal/run-sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sva_code: activeSvaCode,
          dut_code: dutCode || "",
          dut_filename: "dut.sv",
          dut_top: dutModule || "",
          mode: "bmc",
          depth: bmcDepth,
          solver: solver || "",
          timeout: 300,
        }),
      });
      setFormalResult(await resp.json());
    } catch (err) {
      setError(err.message);
    }
    setStep("complete");
    setLoading(false);
  };

  // ── View Lowered RTL ────────────────────────────────────
  const viewLowered = async () => {
    if (!activeSvaCode) return;
    try {
      const resp = await fetch(`${API_BASE}/api/formal/lower`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sva_code: activeSvaCode }),
      });
      setLoweredRtl(await resp.json());
    } catch (err) {
      setError(err.message);
    }
  };

  // ── Analyze Failure ─────────────────────────────────────
  const analyzeFailure = async () => {
    if (!formalResult?.job_id || loading) return;
    setLoading(true);
    setStep("analyzing");
    setDebugAnalysis(null);
    try {
      const resp = await fetch(
        `${API_BASE}/api/formal/debug/${formalResult.job_id}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            dut_code: dutCode || "",
            model: model || undefined,
            temperature: 0.2,
          }),
        },
      );
      const data = await resp.json();
      setDebugAnalysis(data.analysis || data);
    } catch (err) {
      setError(err.message);
    }
    setStep("");
    setLoading(false);
  };

  // ── Re-run After Fix ───────────────────────────────────
  const rerunFormal = async () => {
    if (!activeSvaCode || loading) return;
    setLoading(true);
    setStep("rerunning");
    setRerunResult(null);
    try {
      const resp = await fetch(`${API_BASE}/api/formal/rerun`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sva_code: activeSvaCode,
          dut_code: dutCode || "",
          dut_filename: "dut.sv",
          dut_top: dutModule || "",
          mode: "bmc",
          depth: bmcDepth,
          solver: solver || "",
          timeout: 300,
          previous_job_id: formalResult?.job_id || "",
        }),
      });
      setRerunResult(await resp.json());
    } catch (err) {
      setError(err.message);
    }
    setStep("");
    setLoading(false);
  };

  const applyFix = () => {
    if (debugAnalysis?.fixed_code) {
      if (debugAnalysis.classification === "DESIGN_BUG" && dutCode)
        setDutCode(debugAnalysis.fixed_code);
      else if (pipeline === "sva") setSvaCode(debugAnalysis.fixed_code);
      else
        setSvaResult((prev) =>
          prev ? { ...prev, sva_code: debugAnalysis.fixed_code } : prev,
        );
    }
  };

  const loadExample = (ex) => {
    setDescription(ex.desc);
    setProtocol(ex.protocol || "");
  };
  const v = svaResult?.validation;
  const sources = svaResult?.sources || [];
  const fr = formalResult?.result;
  const isFail = fr?.status === "FAIL";

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
            {"\u{1F9EA}"} Formal Verification
          </div>
          <div style={{ fontSize: 10, color: "#7d8590" }}>
            {pipeline === "english"
              ? "English \u2192 SVA \u2192 Lower \u2192 Prove \u2192 Debug"
              : "SVA \u2192 Lower \u2192 Prove \u2192 Debug"}
          </div>
        </div>

        {/* Pipeline Selector */}
        <div
          style={{
            padding: "8px 16px",
            borderBottom: "1px solid #21262d",
            display: "flex",
            gap: 4,
          }}
        >
          {[
            { id: "english", label: "English \u2192 SVA", icon: "\u{1F4DD}" },
            { id: "sva", label: "Paste SVA", icon: "\u{1F4CB}" },
          ].map((p) => (
            <button
              key={p.id}
              onClick={() => {
                setPipeline(p.id);
                resetResults();
              }}
              style={{
                flex: 1,
                padding: "6px 8px",
                borderRadius: 6,
                border: "none",
                background: pipeline === p.id ? "#58a6ff20" : "#161b22",
                color: pipeline === p.id ? "#58a6ff" : "#7d8590",
                fontSize: 11,
                fontWeight: 600,
                cursor: "pointer",
                fontFamily: "'JetBrains Mono', monospace",
                borderBottom:
                  pipeline === p.id
                    ? "2px solid #58a6ff"
                    : "2px solid transparent",
              }}
            >
              {p.icon} {p.label}
            </button>
          ))}
        </div>

        {/* Pipeline A: English Description */}
        {pipeline === "english" && (
          <div
            style={{ padding: "12px 16px", borderBottom: "1px solid #21262d" }}
          >
            <label style={labelStyle}>Property Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe the property in English..."
              rows={3}
              style={textareaStyle}
            />
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 4,
                marginTop: 8,
              }}
            >
              {EXAMPLE_PROMPTS.map((ex, i) => (
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
        )}

        {/* Pipeline B: Direct SVA Code */}
        {pipeline === "sva" && (
          <div
            style={{ padding: "12px 16px", borderBottom: "1px solid #21262d" }}
          >
            <label style={labelStyle}>
              SVA Code (from Jasper, Questa, or manual)
            </label>
            <textarea
              value={svaCode}
              onChange={(e) => setSvaCode(e.target.value)}
              placeholder={
                "module my_checker (\n    input logic clk,\n    input logic rst_n,\n    input logic valid,\n    input logic ready\n);\n    default clocking cb @(posedge clk); endclocking\n    default disable iff (!rst_n);\n\n    property p_handshake;\n        valid && !ready |=> valid;\n    endproperty\n\n    assert_hs : assert property (p_handshake);\n    cover_hs  : cover property (p_handshake);\nendmodule"
              }
              rows={10}
              style={{
                ...textareaStyle,
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 10,
              }}
            />
          </div>
        )}

        {/* DUT Code */}
        <div
          style={{ padding: "12px 16px", borderBottom: "1px solid #21262d" }}
        >
          <label style={labelStyle}>DUT Code (optional)</label>
          <textarea
            value={dutCode}
            onChange={(e) => setDutCode(e.target.value)}
            placeholder="Paste DUT SystemVerilog here..."
            rows={4}
            style={{
              ...textareaStyle,
              fontSize: 10,
              fontFamily: "'JetBrains Mono', monospace",
            }}
          />
        </div>

        {/* Config */}
        <div
          style={{ padding: "12px 16px", borderBottom: "1px solid #21262d" }}
        >
          <label style={labelStyle}>Configuration</label>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 8,
              marginTop: 6,
            }}
          >
            <div>
              <div style={sublabelStyle}>Clock</div>
              <input
                value={clock}
                onChange={(e) => setClock(e.target.value)}
                style={inputStyle}
              />
            </div>
            <div>
              <div style={sublabelStyle}>Reset</div>
              <input
                value={reset}
                onChange={(e) => setReset(e.target.value)}
                style={inputStyle}
              />
            </div>
            <div>
              <div style={sublabelStyle}>Protocol</div>
              <input
                value={protocol}
                onChange={(e) => setProtocol(e.target.value)}
                placeholder="axi, apb..."
                style={inputStyle}
              />
            </div>
            <div>
              <div style={sublabelStyle}>DUT Module</div>
              <input
                value={dutModule}
                onChange={(e) => setDutModule(e.target.value)}
                placeholder="my_dut"
                style={inputStyle}
              />
            </div>
          </div>
        </div>

        {/* Formal Settings */}
        <div
          style={{ padding: "12px 16px", borderBottom: "1px solid #21262d" }}
        >
          <label style={labelStyle}>Formal Settings</label>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 8,
              marginTop: 6,
            }}
          >
            <div>
              <div style={sublabelStyle}>Solver</div>
              <select
                value={solver}
                onChange={(e) => setSolver(e.target.value)}
                style={{ ...inputStyle, cursor: "pointer" }}
              >
                <option value="">default (yices)</option>
                <option value="yices">yices</option>
                <option value="boolector">boolector</option>
                <option value="z3">z3</option>
              </select>
            </div>
            <div>
              <div style={sublabelStyle}>BMC Depth: {bmcDepth}</div>
              <input
                type="range"
                min={5}
                max={100}
                value={bmcDepth}
                onChange={(e) => setBmcDepth(parseInt(e.target.value))}
                style={{ width: "100%", accentColor: "#58a6ff", height: 4 }}
              />
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div
          style={{
            padding: "12px 16px",
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          {pipeline === "english" && (
            <button
              onClick={generateSVA}
              disabled={!description.trim() || loading}
              style={primaryBtnStyle(!description.trim() || loading, "#58a6ff")}
            >
              {step === "generating"
                ? "\u23F3 Generating SVA..."
                : "\u26A1 Generate SVA"}
            </button>
          )}

          {activeSvaCode && (
            <>
              <button onClick={viewLowered} style={secondaryBtnStyle}>
                {"\u{1F50D}"} View Lowered RTL
              </button>
              <button
                onClick={runFormal}
                disabled={loading}
                style={primaryBtnStyle(loading, "#238636")}
              >
                {step === "proving"
                  ? "\u23F3 Running SymbiYosys..."
                  : "\u{1F9EA} Run Formal Proof"}
              </button>
            </>
          )}

          {isFail && (
            <button
              onClick={analyzeFailure}
              disabled={loading}
              style={primaryBtnStyle(loading, "#bc8cff")}
            >
              {step === "analyzing"
                ? "\u23F3 Analyzing..."
                : "\u{1F41B} Analyze Failure"}
            </button>
          )}

          {debugAnalysis && (
            <button
              onClick={rerunFormal}
              disabled={loading}
              style={primaryBtnStyle(loading, "#d29922")}
            >
              {step === "rerunning"
                ? "\u23F3 Re-running..."
                : "\u{1F504} Re-run After Fix"}
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
          overflowY: "auto",
          background: "#010409",
        }}
      >
        {!svaResult && !formalResult && !loweredRtl && !error && (
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
                background: "linear-gradient(135deg, #58a6ff18, #bc8cff18)",
                border: "1px solid #21262d",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 24,
              }}
            >
              {"\u{1F9EA}"}
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>
                Formal Verification Pipeline
              </div>
              <div
                style={{
                  fontSize: 11,
                  color: "#7d8590",
                  maxWidth: 380,
                  lineHeight: 1.5,
                }}
              >
                {pipeline === "english"
                  ? "Describe a property in English \u2192 Generate SVA \u2192 Lower to RTL \u2192 Prove with SymbiYosys \u2192 AI Debug on failure."
                  : "Paste your existing SVA (from Jasper, Questa, or manual) \u2192 Lower to synthesizable RTL \u2192 Prove with SymbiYosys \u2192 AI Debug on failure."}
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

        {/* Re-run Result */}
        {rerunResult && (
          <div
            style={{
              padding: 16,
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
          >
            <div
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: "#7d8590",
                borderBottom: "1px solid #21262d",
                paddingBottom: 4,
              }}
            >
              Re-run Result
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <FormalBadge status={rerunResult.result?.status || "ERROR"} />
              {rerunResult.fix_verdict && (
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 700,
                    padding: "3px 10px",
                    borderRadius: 5,
                    fontFamily: "'JetBrains Mono', monospace",
                    background:
                      rerunResult.fix_verdict === "FIXED"
                        ? "#23863620"
                        : "#f8514920",
                    color:
                      rerunResult.fix_verdict === "FIXED"
                        ? "#3fb950"
                        : "#f85149",
                  }}
                >
                  {rerunResult.fix_verdict}
                </span>
              )}
            </div>
            {rerunResult.fix_message && (
              <div
                style={{
                  fontSize: 11,
                  color: "#e6edf3",
                  background: "#161b22",
                  border: "1px solid #21262d",
                  borderRadius: 6,
                  padding: "8px 12px",
                }}
              >
                {rerunResult.fix_message}
              </div>
            )}
          </div>
        )}

        {/* Debug Analysis */}
        {debugAnalysis && (
          <div
            style={{
              padding: 16,
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
          >
            <div
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: "#7d8590",
                borderBottom: "1px solid #21262d",
                paddingBottom: 4,
              }}
            >
              {"\u{1F41B}"} AI Debug Analysis
            </div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                flexWrap: "wrap",
              }}
            >
              <ClassificationBadge
                classification={debugAnalysis.classification}
              />
              {debugAnalysis.violation_cycle >= 0 && (
                <StatBadge
                  label="cycle"
                  value={debugAnalysis.violation_cycle}
                />
              )}
              {debugAnalysis.violation_assertion && (
                <StatBadge
                  label="assertion"
                  value={debugAnalysis.violation_assertion}
                />
              )}
            </div>
            {debugAnalysis.summary && (
              <div style={{ fontSize: 12, color: "#e6edf3", lineHeight: 1.5 }}>
                {debugAnalysis.summary}
              </div>
            )}
            {debugAnalysis.root_cause && (
              <div>
                <div
                  style={{
                    fontSize: 10,
                    fontWeight: 600,
                    color: "#7d8590",
                    marginBottom: 4,
                    textTransform: "uppercase",
                    letterSpacing: 1,
                  }}
                >
                  Root Cause
                </div>
                <div
                  style={{
                    fontSize: 11,
                    color: "#e6edf3",
                    lineHeight: 1.6,
                    background: "#161b22",
                    border: "1px solid #21262d",
                    borderRadius: 6,
                    padding: "8px 12px",
                  }}
                >
                  {debugAnalysis.root_cause}
                </div>
              </div>
            )}
            {debugAnalysis.fixed_code && (
              <div>
                <CodeBlock
                  code={debugAnalysis.fixed_code}
                  title="Suggested Fix"
                />
                <button
                  onClick={applyFix}
                  style={{
                    ...secondaryBtnStyle,
                    marginTop: 6,
                    background: "#23863615",
                    borderColor: "#23863640",
                    color: "#3fb950",
                  }}
                >
                  {"\u2713"} Apply Fix
                </button>
              </div>
            )}
          </div>
        )}

        {/* Formal Result */}
        {formalResult && (
          <div
            style={{
              padding: 16,
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
          >
            <div
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: "#7d8590",
                borderBottom: "1px solid #21262d",
                paddingBottom: 4,
              }}
            >
              Formal Proof Result
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <FormalBadge
                status={fr?.status || formalResult.status || "ERROR"}
              />
              {formalResult.timing && (
                <div
                  style={{
                    fontSize: 10,
                    color: "#7d8590",
                    fontFamily: "'JetBrains Mono', monospace",
                  }}
                >
                  lower: {formalResult.timing.lowering_seconds}s {"\u2022"}{" "}
                  prove: {formalResult.timing.proving_seconds}s {"\u2022"}{" "}
                  total: {formalResult.timing.total_seconds}s
                </div>
              )}
            </div>
            {fr?.failed_assertions?.length > 0 && (
              <div
                style={{
                  background: "#f8514910",
                  border: "1px solid #f8514920",
                  borderRadius: 6,
                  padding: "8px 12px",
                }}
              >
                <div
                  style={{
                    fontSize: 10,
                    fontWeight: 600,
                    color: "#f85149",
                    marginBottom: 4,
                  }}
                >
                  Failed Assertions:
                </div>
                {fr.failed_assertions.map((fa, i) => (
                  <div
                    key={i}
                    style={{
                      fontSize: 11,
                      color: "#f85149",
                      marginBottom: 2,
                      fontFamily: "'JetBrains Mono', monospace",
                    }}
                  >
                    {"\u2717"} {fa.name} at step {fa.step}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Lowered RTL */}
        {loweredRtl && (
          <div
            style={{
              padding: 16,
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
          >
            <div
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: "#7d8590",
                borderBottom: "1px solid #21262d",
                paddingBottom: 4,
              }}
            >
              Lowered RTL (synthesizable monitor)
            </div>
            {loweredRtl.parsed_summary && (
              <details>
                <summary
                  style={{ fontSize: 10, color: "#7d8590", cursor: "pointer" }}
                >
                  Parse summary
                </summary>
                <pre
                  style={{
                    marginTop: 4,
                    background: "#0d1117",
                    border: "1px solid #21262d",
                    borderRadius: 6,
                    padding: 8,
                    fontSize: 10,
                    color: "#7d8590",
                    fontFamily: "'JetBrains Mono', monospace",
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {loweredRtl.parsed_summary}
                </pre>
              </details>
            )}
            {loweredRtl.lowered_rtl && (
              <CodeBlock code={loweredRtl.lowered_rtl} />
            )}
          </div>
        )}

        {/* SVA Result (Pipeline A only) */}
        {svaResult && pipeline === "english" && (
          <div
            style={{
              padding: 16,
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
          >
            <div
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: "#7d8590",
                borderBottom: "1px solid #21262d",
                paddingBottom: 4,
              }}
            >
              Generated SVA
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              <Badge ok={v?.sva2sby_compatible} label="sva2sby Compatible" />
              <Badge
                ok={v?.stats?.assertions > 0 || v?.stats?.covers > 0}
                label="Has Assert/Cover"
              />
              <Badge ok={v?.stats?.has_default_clocking} label="Clocking" />
              <Badge ok={v?.stats?.has_disable_iff} label="Reset" />
            </div>
            {svaResult.sva_code && <CodeBlock code={svaResult.sva_code} />}
          </div>
        )}
      </div>
    </div>
  );
}

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
  minHeight: 60,
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
const primaryBtnStyle = (disabled, color) => ({
  padding: "8px 12px",
  borderRadius: 6,
  border: "none",
  background: disabled ? "#21262d" : color,
  color: disabled ? "#7d8590" : "#000",
  fontSize: 12,
  fontWeight: 600,
  cursor: disabled ? "not-allowed" : "pointer",
  fontFamily: "inherit",
});
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
