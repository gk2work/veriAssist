import { useState, useRef, useEffect, useCallback } from "react";
import { API_BASE } from "../config/constants";

// ── Constants ─────────────────────────────────────────────────

const SOLVERS = [
  { id: "boolector", label: "Boolector", desc: "Fast BMC solver (recommended)" },
  { id: "yices", label: "Yices 2", desc: "SMT, good for k-induction" },
  { id: "z3", label: "Z3", desc: "General-purpose SMT solver" },
];

const MODES = [
  { id: "bmc", label: "BMC", desc: "Bounded Model Checking" },
  { id: "prove", label: "Prove", desc: "k-Induction proof" },
  { id: "cover", label: "Cover", desc: "Cover reachability" },
];

const FILTER_OPTIONS = [
  { id: "all", label: "No filter" },
  { id: "assert", label: "Assert only" },
  { id: "cover", label: "Cover only" },
  { id: "pass", label: "PASS only" },
  { id: "fail", label: "FAIL only" },
];

const POLL_INTERVAL_MS = 2000;

// ── Status color helpers ───────────────────────────────────────

function statusColor(status) {
  if (status === "PASS") return "#3fb950";
  if (status === "FAIL") return "#f85149";
  if (status === "SKIPPED") return "#7d8590";
  if (status === "ERROR") return "#f85149";
  return "#d29922";
}

function statusIcon(status) {
  if (status === "PASS") return "✓";
  if (status === "FAIL") return "✗";
  if (status === "SKIPPED") return "–";
  return "⚠";
}

function jobPhaseLabel(status) {
  const map = {
    queued: "Queued...",
    generating_sva: "Generating SVA...",
    lowering: "Lowering SVA to RTL...",
    proving: "Running formal proof...",
    complete: "Complete",
    failed: "Failed",
  };
  return map[status] || status;
}

function logLineColor(line) {
  const l = line.toLowerCase();
  if (l.includes("error") || l.includes("fail") || l.includes("[error]")) return "#f85149";
  if (l.includes("warning") || l.includes("warn")) return "#d29922";
  if (l.startsWith("info") || l.includes("[info]")) return "#3fb950";
  return "#8b949e";
}

function assertionHasTrace(assertion) {
  return Boolean(assertion?.counterexample_vcd || assertion?.tracefile);
}

function shortPath(path) {
  return path ? path.split("/").pop() : "—";
}

function isBinaryValue(value) {
  return typeof value === "string" && /^[01xz-]$/i.test(value);
}

function isBusValue(value) {
  return typeof value === "string" && /^[01xz-]+$/i.test(value) && value.length > 1;
}

function parseWaveNumericValue(value) {
  if (!value || typeof value !== "string") return null;
  if (/^[01]+$/i.test(value)) return Number.parseInt(value, 2);
  if (/^\d+$/.test(value)) return Number.parseInt(value, 10);
  return null;
}

function buildWaveSamples(signal, timepoints) {
  const transitions = signal?.transitions || [];
  const samples = [];
  let cursor = 0;
  let currentValue = signal?.initial_value || "x";

  for (const time of timepoints) {
    while (cursor < transitions.length && transitions[cursor].time <= time) {
      currentValue = transitions[cursor].value;
      cursor += 1;
    }
    samples.push(currentValue || "x");
  }

  return samples;
}

function resolveFailureMarkerTime(signalDetails, failureStep) {
  if (!Number.isFinite(failureStep) || failureStep < 0) return null;
  const smtStep = (signalDetails || []).find(
    (signal) =>
      signal?.name === "smt_step" || signal?.full_name?.endsWith(".smt_step")
  );
  if (!smtStep) return null;

  for (const transition of smtStep.transitions || []) {
    if (parseWaveNumericValue(transition.value) === failureStep) {
      return transition.time;
    }
  }

  return null;
}

// ── Sub-components ─────────────────────────────────────────────

function SectionLabel({ children }) {
  return (
    <div
      style={{
        fontSize: 10,
        fontWeight: 700,
        color: "#7d8590",
        textTransform: "uppercase",
        letterSpacing: "0.08em",
        marginBottom: 6,
        marginTop: 14,
      }}
    >
      {children}
    </div>
  );
}

function FileDropZone({ label, accept, files, onAdd, onRemove }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  function handleDrop(e) {
    e.preventDefault();
    setDragging(false);
    const dropped = Array.from(e.dataTransfer.files).filter((f) =>
      accept.some((ext) => f.name.endsWith(ext))
    );
    if (dropped.length) onAdd(dropped);
  }

  function handleChange(e) {
    const picked = Array.from(e.target.files);
    if (picked.length) onAdd(picked);
    e.target.value = "";
  }

  return (
    <div>
      <SectionLabel>{label}</SectionLabel>
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        style={{
          border: `1.5px dashed ${dragging ? "#58a6ff" : "#30363d"}`,
          borderRadius: 6,
          padding: "10px 12px",
          cursor: "pointer",
          background: dragging ? "#58a6ff0d" : "#161b22",
          transition: "border-color 0.15s, background 0.15s",
          minHeight: 48,
        }}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={accept.join(",")}
          style={{ display: "none" }}
          onChange={handleChange}
        />
        {files.length === 0 ? (
          <div style={{ color: "#484f58", fontSize: 11, textAlign: "center" }}>
            Drop {accept.join(", ")} files here or click to browse
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {files.map((f, i) => (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 6,
                }}
              >
                <span
                  style={{
                    fontSize: 11,
                    fontFamily: "'JetBrains Mono', monospace",
                    color: "#58a6ff",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {f.name}
                </span>
                <button
                  onClick={(e) => { e.stopPropagation(); onRemove(i); }}
                  style={{
                    background: "none",
                    border: "none",
                    color: "#484f58",
                    cursor: "pointer",
                    fontSize: 13,
                    padding: "0 2px",
                    lineHeight: 1,
                    flexShrink: 0,
                  }}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function SelectInput({ value, onChange, options }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      style={{
        width: "100%",
        background: "#161b22",
        color: "#e6edf3",
        border: "1px solid #30363d",
        borderRadius: 4,
        padding: "5px 8px",
        fontSize: 12,
        fontFamily: "'JetBrains Mono', monospace",
        cursor: "pointer",
      }}
    >
      {options.map((o) => (
        <option key={o.id} value={o.id}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

function TextInput({ value, onChange, placeholder }) {
  return (
    <input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      style={{
        width: "100%",
        background: "#161b22",
        color: "#e6edf3",
        border: "1px solid #30363d",
        borderRadius: 4,
        padding: "5px 8px",
        fontSize: 12,
        fontFamily: "'JetBrains Mono', monospace",
        boxSizing: "border-box",
      }}
    />
  );
}

function SummaryBar({ result, depth }) {
  if (!result) return null;
  const s = result.assertion_summary || {};
  const assertions = result.assertions || [];
  const covers = assertions.filter((a) => a.type === "COVER");
  const asserts = assertions.filter((a) => a.type === "ASSERT");
  const coveredCount = covers.filter((a) => a.status === "PASS").length;
  const unreachableCount = covers.filter((a) => a.status === "SKIPPED").length;

  const items = [
    { label: "Properties", value: assertions.length, color: "#e6edf3" },
    {
      label: "Assertions",
      value: `${s.passed || 0} / ${s.total || 0} proven`,
      color: s.failed ? "#f85149" : "#3fb950",
    },
    {
      label: "Covers",
      value: `${coveredCount} / ${covers.length} covered`,
      color: coveredCount === covers.length && covers.length > 0 ? "#3fb950" : "#d29922",
    },
    { label: "Unreachable", value: unreachableCount, color: "#7d8590" },
    {
      label: "Elapsed",
      value: `${(result.elapsed_seconds || 0).toFixed(1)}s`,
      color: "#8b949e",
    },
    { label: "Depth", value: result.depth_reached || depth, color: "#8b949e" },
  ];

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "0 24px",
        padding: "8px 16px",
        background: "#0d1117",
        borderBottom: "1px solid #21262d",
        fontSize: 11,
        fontFamily: "'JetBrains Mono', monospace",
      }}
    >
      {items.map((item) => (
        <span key={item.label} style={{ color: "#7d8590" }}>
          {item.label}:{" "}
          <span style={{ color: item.color, fontWeight: 600 }}>{item.value}</span>
        </span>
      ))}
    </div>
  );
}

function PropertyTable({ result, solver, depth, filter, onOpenTrace }) {
  const assertions = result?.assertions || [];

  const filtered = assertions.filter((a) => {
    if (filter === "assert") return a.type === "ASSERT";
    if (filter === "cover") return a.type === "COVER";
    if (filter === "pass") return a.status === "PASS";
    if (filter === "fail") return a.status === "FAIL";
    return true;
  });

  const th = {
    padding: "6px 10px",
    textAlign: "left",
    fontSize: 10,
    fontWeight: 700,
    color: "#7d8590",
    textTransform: "uppercase",
    letterSpacing: "0.06em",
    borderBottom: "1px solid #21262d",
    background: "#0d1117",
    whiteSpace: "nowrap",
    userSelect: "none",
  };

  const td = {
    padding: "5px 10px",
    fontSize: 11,
    fontFamily: "'JetBrains Mono', monospace",
    borderBottom: "1px solid #161b22",
    whiteSpace: "nowrap",
    overflow: "hidden",
    maxWidth: 260,
    textOverflow: "ellipsis",
  };

  if (filtered.length === 0) {
    return (
      <div
        style={{
          padding: 32,
          textAlign: "center",
          color: "#484f58",
          fontSize: 12,
        }}
      >
        No properties match the current filter.
      </div>
    );
  }

  return (
    <div style={{ overflow: "auto", flex: 1 }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ ...th, width: 28 }}></th>
            <th style={th}>Type</th>
            <th style={{ ...th, maxWidth: 300 }}>Name</th>
            <th style={th}>Engine</th>
            <th style={th}>Bound</th>
            <th style={th}>Time</th>
            <th style={th}>Task</th>
            <th style={th}>Traces</th>
            <th style={th}>Source</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map((a, i) => {
            const color = statusColor(a.status);
            const icon = statusIcon(a.status);
            const typeLabel =
              a.type === "ASSERT"
                ? "Assert"
                : a.type === "COVER"
                ? "Cover"
                : a.type === "ASSUME"
                ? "Assume"
                : a.type || "—";
            const bound =
              a.status === "FAIL" && a.step > 0 ? `N (${a.step})` : depth || "—";
            const hasTrace = assertionHasTrace(a);
            const rowBg = i % 2 === 0 ? "#0d1117" : "#010409";

            return (
              <tr key={i} style={{ background: rowBg }}>
                <td style={{ ...td, textAlign: "center", color }}>
                  <span style={{ fontWeight: 700, fontSize: 13 }}>{icon}</span>
                </td>
                <td style={{ ...td, color: "#8b949e" }}>{typeLabel}</td>
                <td
                  style={{ ...td, color: "#e6edf3", maxWidth: 300 }}
                  title={a.name}
                >
                  {hasTrace ? (
                    <button
                      onClick={() => onOpenTrace?.(a)}
                      style={{
                        background: "none",
                        border: "none",
                        padding: 0,
                        margin: 0,
                        color: a.status === "FAIL" ? "#ff7b72" : "#e6edf3",
                        cursor: "pointer",
                        font: "inherit",
                        textAlign: "left",
                      }}
                      title={`Open waveform for ${a.name}`}
                    >
                      {a.name}
                    </button>
                  ) : (
                    a.name
                  )}
                </td>
                <td style={{ ...td, color: "#58a6ff" }}>
                  {solver || "smtbmc"}
                </td>
                <td style={{ ...td, color: "#d29922" }}>{bound}</td>
                <td style={{ ...td, color: "#8b949e" }}>
                  {result.elapsed_seconds
                    ? `${(result.elapsed_seconds / Math.max(filtered.length, 1)).toFixed(2)}s`
                    : "—"}
                </td>
                <td style={{ ...td, color: "#7d8590" }}>&lt;embedded&gt;</td>
                <td style={{ ...td, color: "#8b949e" }}>
                  {hasTrace ? (
                    <button
                      onClick={() => onOpenTrace?.(a)}
                      style={{
                        background: "#1f6feb1a",
                        border: "1px solid #1f6feb55",
                        color: "#58a6ff",
                        borderRadius: 4,
                        padding: "2px 8px",
                        cursor: "pointer",
                        fontSize: 10,
                        fontFamily: "'JetBrains Mono', monospace",
                      }}
                      title={`Open waveform for ${a.name}`}
                    >
                      View
                    </button>
                  ) : (
                    0
                  )}
                </td>
                <td style={{ ...td, color: "#7d8590" }}>VeriAssist</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div
        style={{
          padding: "6px 12px",
          fontSize: 11,
          color: "#484f58",
          borderTop: "1px solid #21262d",
          fontFamily: "'JetBrains Mono', monospace",
        }}
      >
        Total: {assertions.length} &nbsp;|&nbsp; Filtered: {filtered.length}{" "}
        &nbsp;|&nbsp; Selected: 0
      </div>
    </div>
  );
}

function WaveformModal({ state, onClose }) {
  const waveform = state.data?.vcd_data;
  const signalDetails = waveform?.signal_details || [];
  const markerTime = resolveFailureMarkerTime(
    signalDetails,
    Number.isFinite(state.assertion?.step) ? state.assertion.step : -1
  );

  useEffect(() => {
    if (!state.open) return undefined;
    function handleKeydown(event) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeydown);
    return () => window.removeEventListener("keydown", handleKeydown);
  }, [state.open, onClose]);

  if (!state.open) return null;

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(1, 4, 9, 0.78)",
        zIndex: 1000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
    >
      <div
        onClick={(event) => event.stopPropagation()}
        style={{
          width: "min(1180px, 100%)",
          height: "min(820px, 100%)",
          background: "#0d1117",
          border: "1px solid #30363d",
          borderRadius: 10,
          boxShadow: "0 24px 80px rgba(0, 0, 0, 0.45)",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            padding: "14px 16px 12px",
            borderBottom: "1px solid #21262d",
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: 16,
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div
              style={{
                fontSize: 12,
                fontWeight: 700,
                color: "#58a6ff",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                marginBottom: 6,
              }}
            >
              Counterexample Waveform
            </div>
            <div
              style={{
                fontSize: 14,
                color: "#e6edf3",
                fontFamily: "'JetBrains Mono', monospace",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {state.assertion?.name || "Failed assertion"}
            </div>
            <div
              style={{
                marginTop: 8,
                display: "flex",
                flexWrap: "wrap",
                gap: "6px 14px",
                fontSize: 11,
                color: "#7d8590",
                fontFamily: "'JetBrains Mono', monospace",
              }}
            >
              <span>trace: {shortPath(state.data?.vcd_path)}</span>
              <span>timescale: {waveform?.timescale || "—"}</span>
              <span>signals: {waveform?.signal_count || 0}</span>
              {Number.isFinite(state.assertion?.step) && state.assertion.step > 0 && (
                <span>failed step: {state.assertion.step}</span>
              )}
            </div>
          </div>

          <button
            onClick={onClose}
            style={{
              background: "#161b22",
              border: "1px solid #30363d",
              color: "#8b949e",
              borderRadius: 6,
              fontSize: 12,
              padding: "6px 10px",
              cursor: "pointer",
              flexShrink: 0,
            }}
          >
            Close
          </button>
        </div>

        <div style={{ flex: 1, minHeight: 0, background: "#010409" }}>
          {state.loading ? (
            <div
              style={{
                height: "100%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#58a6ff",
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 12,
              }}
            >
              Loading waveform...
            </div>
          ) : state.error ? (
            <div
              style={{
                height: "100%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                padding: 24,
                textAlign: "center",
                color: "#f85149",
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 12,
              }}
            >
              {state.error}
            </div>
          ) : (
            <WaveformViewer
              waveform={waveform}
              markerTime={markerTime}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function WaveformViewer({ waveform, markerTime }) {
  const timepoints = waveform?.timepoints || [];
  const signalDetails = waveform?.signal_details || [];

  if (!timepoints.length || !signalDetails.length) {
    return (
      <div
        style={{
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#7d8590",
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 12,
        }}
      >
        No waveform data available for this trace.
      </div>
    );
  }

  const labelWidth = 250;
  const stepWidth = timepoints.length > 18 ? 48 : 64;
  const axisHeight = 44;

  return (
    <div style={{ height: "100%", overflow: "auto" }}>
      <div style={{ minWidth: labelWidth + timepoints.length * stepWidth }}>
        <div
          style={{
            position: "sticky",
            top: 0,
            zIndex: 2,
            display: "flex",
            borderBottom: "1px solid #21262d",
            background: "#0d1117",
          }}
        >
          <div
            style={{
              width: labelWidth,
              minWidth: labelWidth,
              padding: "12px 14px",
              borderRight: "1px solid #21262d",
              color: "#7d8590",
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
            }}
          >
            Signals
          </div>
          <WaveformAxis
            timepoints={timepoints}
            stepWidth={stepWidth}
            axisHeight={axisHeight}
            markerTime={markerTime}
          />
        </div>

        {signalDetails.map((signal) => (
          <WaveformRow
            key={signal.full_name}
            signal={signal}
            timepoints={timepoints}
            stepWidth={stepWidth}
            labelWidth={labelWidth}
            markerTime={markerTime}
          />
        ))}
      </div>
    </div>
  );
}

function WaveformAxis({ timepoints, stepWidth, axisHeight, markerTime }) {
  const width = Math.max(timepoints.length * stepWidth, stepWidth);
  const markerIndex = markerTime == null ? -1 : timepoints.indexOf(markerTime);
  const markerX = markerIndex >= 0 ? markerIndex * stepWidth : null;

  return (
    <svg width={width} height={axisHeight} style={{ display: "block", background: "#0d1117" }}>
      {timepoints.map((time, index) => {
        const x = index * stepWidth;
        return (
          <g key={time}>
            <line x1={x} x2={x} y1={0} y2={axisHeight} stroke="#21262d" />
            <text
              x={x + 6}
              y={16}
              fill="#7d8590"
              fontSize="10"
              fontFamily="'JetBrains Mono', monospace"
            >
              {time}
            </text>
          </g>
        );
      })}
      <line x1={width} x2={width} y1={0} y2={axisHeight} stroke="#21262d" />
      {markerX != null && (
        <line x1={markerX} x2={markerX} y1={0} y2={axisHeight} stroke="#f85149" strokeDasharray="4 4" />
      )}
    </svg>
  );
}

function WaveformRow({ signal, timepoints, stepWidth, labelWidth, markerTime }) {
  const samples = buildWaveSamples(signal, timepoints);
  const width = Math.max(timepoints.length * stepWidth, stepWidth);
  const rowHeight = 34;
  const isSingleBit =
    signal.width === 1 && samples.every((value) => isBinaryValue(value));
  const markerIndex = markerTime == null ? -1 : timepoints.indexOf(markerTime);
  const markerX = markerIndex >= 0 ? markerIndex * stepWidth : null;

  return (
    <div style={{ display: "flex", borderBottom: "1px solid #161b22" }}>
      <div
        style={{
          width: labelWidth,
          minWidth: labelWidth,
          padding: "8px 12px",
          borderRight: "1px solid #21262d",
          background: "#0d1117",
        }}
      >
        <div
          title={signal.full_name}
          style={{
            fontSize: 11,
            color: "#e6edf3",
            fontFamily: "'JetBrains Mono', monospace",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {signal.full_name}
        </div>
        <div
          style={{
            marginTop: 4,
            fontSize: 10,
            color: "#7d8590",
            fontFamily: "'JetBrains Mono', monospace",
          }}
        >
          {signal.width}b • {signal.final_value}
        </div>
      </div>

      <svg width={width} height={rowHeight} style={{ display: "block", background: "#010409" }}>
        {timepoints.map((time, index) => {
          const x = index * stepWidth;
          return (
            <line
              key={`${signal.full_name}-${time}`}
              x1={x}
              x2={x}
              y1={0}
              y2={rowHeight}
              stroke="#161b22"
            />
          );
        })}
        <line x1={width} x2={width} y1={0} y2={rowHeight} stroke="#161b22" />
        {markerX != null && (
          <line x1={markerX} x2={markerX} y1={0} y2={rowHeight} stroke="#f85149" strokeDasharray="4 4" />
        )}

        {isSingleBit ? (
          <DigitalWave samples={samples} stepWidth={stepWidth} rowHeight={rowHeight} />
        ) : (
          <BusWave samples={samples} stepWidth={stepWidth} rowHeight={rowHeight} />
        )}
      </svg>
    </div>
  );
}

function DigitalWave({ samples, stepWidth, rowHeight }) {
  const highY = 8;
  const lowY = rowHeight - 8;
  const midY = rowHeight / 2;

  function sampleY(value) {
    const normalized = (value || "x").toLowerCase();
    if (normalized === "1") return highY;
    if (normalized === "0") return lowY;
    return midY;
  }

  return (
    <>
      {samples.map((value, index) => {
        const x1 = index * stepWidth;
        const x2 = x1 + stepWidth;
        const normalized = (value || "x").toLowerCase();
        const y = sampleY(normalized);
        const previous = index > 0 ? (samples[index - 1] || "x").toLowerCase() : normalized;
        const previousY = sampleY(previous);
        const stroke =
          normalized === "1" || normalized === "0" ? "#3fb950" : "#d29922";

        return (
          <g key={`${index}-${normalized}`}>
            {index > 0 && previous !== normalized && (
              <line x1={x1} x2={x1} y1={previousY} y2={y} stroke={stroke} strokeWidth="1.5" />
            )}
            <line x1={x1} x2={x2} y1={y} y2={y} stroke={stroke} strokeWidth="1.5" />
            {(normalized === "x" || normalized === "z" || normalized === "-") && (
              <text
                x={x1 + stepWidth / 2}
                y={midY + 4}
                textAnchor="middle"
                fill="#d29922"
                fontSize="10"
                fontFamily="'JetBrains Mono', monospace"
              >
                {normalized}
              </text>
            )}
          </g>
        );
      })}
    </>
  );
}

function BusWave({ samples, stepWidth, rowHeight }) {
  return (
    <>
      {samples.map((value, index) => {
        const x = index * stepWidth;
        const normalized = value || "x";
        const isKnown = isBusValue(normalized) || /^\d+$/.test(normalized);
        const fill = isKnown ? "#1f6feb22" : "#d299221c";
        const stroke = isKnown ? "#58a6ff" : "#d29922";

        return (
          <g key={`${index}-${normalized}`}>
            <rect
              x={x + 4}
              y={8}
              width={Math.max(stepWidth - 8, 8)}
              height={rowHeight - 16}
              rx="4"
              fill={fill}
              stroke={stroke}
            />
            <text
              x={x + stepWidth / 2}
              y={rowHeight / 2 + 4}
              textAnchor="middle"
              fill={stroke}
              fontSize="10"
              fontFamily="'JetBrains Mono', monospace"
            >
              {normalized.length > 12 ? `${normalized.slice(0, 9)}...` : normalized}
            </text>
          </g>
        );
      })}
    </>
  );
}

function LogViewer({ logs }) {
  const raw =
    logs?.sby_log || logs?.stdout || logs?.engine_log || "";
  const lines = raw.split("\n").filter(Boolean);

  if (!lines.length) return null;

  return (
    <div
      style={{
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 10.5,
        lineHeight: 1.5,
        padding: "10px 14px",
        overflowY: "auto",
        maxHeight: 420,
        background: "#010409",
      }}
    >
      {lines.map((line, i) => (
        <div key={i} style={{ color: logLineColor(line) }}>
          {line}
        </div>
      ))}
    </div>
  );
}

// ── Main FVPanel ───────────────────────────────────────────────

export default function FVPanel() {
  const [designFiles, setDesignFiles] = useState([]);
  const [svaFiles, setSvaFiles] = useState([]);
  const [mode, setMode] = useState("bmc");
  const [depth, setDepth] = useState(20);
  const [solver, setSolver] = useState("boolector");
  const [topModule, setTopModule] = useState("");
  const [timeout, setTimeout_] = useState(300);

  const [jobId, setJobId] = useState(null);
  const [jobData, setJobData] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");
  const [logExpanded, setLogExpanded] = useState(false);
  const [waveformState, setWaveformState] = useState({
    open: false,
    loading: false,
    error: "",
    assertion: null,
    data: null,
  });

  const pollRef = useRef(null);

  // Polling
  const startPolling = useCallback((id) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/formal/status/${id}`);
        const data = await res.json();
        setJobData(data);
        if (data.status === "complete" || data.status === "failed") {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setRunning(false);
          // Auto-expand log on error so user can see what went wrong
          if (data.result?.status === "ERROR" || data.status === "failed") {
            setLogExpanded(true);
          }
        }
      } catch {
        clearInterval(pollRef.current);
        pollRef.current = null;
        setRunning(false);
      }
    }, POLL_INTERVAL_MS);
  }, []);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  async function handleRun() {
    if (designFiles.length === 0 && svaFiles.length === 0) {
      setError("Upload at least one design file or SVA file.");
      return;
    }
    setError("");
    setRunning(true);
    setJobId(null);
    setJobData(null);
    setLogExpanded(false);

    const form = new FormData();
    designFiles.forEach((f) => form.append("design_files", f));
    // FastAPI requires at least one file; send a blank placeholder if no SVA files
    if (svaFiles.length > 0) {
      svaFiles.forEach((f) => form.append("sva_files", f));
    } else {
      // Append an empty SVA placeholder so the field is present
      form.append("sva_files", new Blob([""], { type: "text/plain" }), "_empty.sva");
    }
    form.append("mode", mode);
    form.append("depth", String(depth));
    form.append("solver", solver);
    form.append("timeout", String(timeout));
    form.append("top_module", topModule);

    try {
      const res = await fetch(`${API_BASE}/api/formal/run-upload`, {
        method: "POST",
        body: form,
      });
      const data = await res.json();

      if (data.error) {
        setError(data.error + (data.message ? ` — ${data.message}` : ""));
        setRunning(false);
        return;
      }

      setJobData(data);
      setJobId(data.job_id);

      if (data.status !== "complete" && data.status !== "failed") {
        startPolling(data.job_id);
      } else {
        setRunning(false);
        if (data.result?.status === "ERROR" || data.status === "failed") {
          setLogExpanded(true);
        }
      }
    } catch (e) {
      setError(`Network error: ${e.message}`);
      setRunning(false);
    }
  }

  function handleReset() {
    if (pollRef.current) clearInterval(pollRef.current);
    setDesignFiles([]);
    setSvaFiles([]);
    setJobId(null);
    setJobData(null);
    setRunning(false);
    setError("");
    setFilter("all");
    setLogExpanded(false);
    setWaveformState({
      open: false,
      loading: false,
      error: "",
      assertion: null,
      data: null,
    });
  }

  const closeWaveform = useCallback(() => {
    setWaveformState((prev) => ({
      ...prev,
      open: false,
      loading: false,
    }));
  }, []);

  const openWaveform = useCallback(
    async (assertion) => {
      if (!jobId || !assertionHasTrace(assertion)) return;

      setWaveformState({
        open: true,
        loading: true,
        error: "",
        assertion,
        data: null,
      });

      try {
        const query = new URLSearchParams({ assertion: assertion.name || "" });
        const response = await fetch(
          `${API_BASE}/api/formal/counterexample/${jobId}?${query.toString()}`
        );
        const data = await response.json();

        if (!response.ok || data.error) {
          throw new Error(data.error || `Failed to load waveform (${response.status})`);
        }

        setWaveformState({
          open: true,
          loading: false,
          error: "",
          assertion,
          data,
        });
      } catch (loadError) {
        setWaveformState({
          open: true,
          loading: false,
          error: loadError.message || "Failed to load waveform.",
          assertion,
          data: null,
        });
      }
    },
    [jobId]
  );

  const result = jobData?.result;
  const jobStatus = jobData?.status;
  const overallStatus = result?.status;

  // Overall badge color
  function overallBadgeStyle() {
    if (overallStatus === "PASS") return { bg: "#23863620", color: "#3fb950", border: "#23863650" };
    if (overallStatus === "FAIL") return { bg: "#f8514920", color: "#f85149", border: "#f8514940" };
    if (overallStatus === "TIMEOUT") return { bg: "#d2922220", color: "#d29922", border: "#d2922240" };
    if (overallStatus === "ERROR") return { bg: "#f8514920", color: "#f85149", border: "#f8514940" };
    return null;
  }
  const badge = overallBadgeStyle();

  // Sidebar width
  const SIDEBAR_W = 272;

  return (
    <div style={{ display: "flex", height: "100%", overflow: "hidden" }}>
      {/* ── Left config sidebar ── */}
      <div
        style={{
          width: SIDEBAR_W,
          minWidth: SIDEBAR_W,
          background: "#0d1117",
          borderRight: "1px solid #21262d",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "12px 14px 8px",
            borderBottom: "1px solid #21262d",
            fontSize: 11,
            fontWeight: 700,
            color: "#58a6ff",
            letterSpacing: "0.04em",
            flexShrink: 0,
          }}
        >
          Design Setup
        </div>

        {/* Scrollable config area */}
        <div style={{ flex: 1, overflowY: "auto", padding: "0 14px 14px" }}>
          <FileDropZone
            label="Design Files (.sv / .v)"
            accept={[".sv", ".v"]}
            files={designFiles}
            onAdd={(f) => setDesignFiles((prev) => [...prev, ...f])}
            onRemove={(i) => setDesignFiles((prev) => prev.filter((_, idx) => idx !== i))}
          />

          <FileDropZone
            label="SVA Files (.sv / .sva)"
            accept={[".sv", ".sva"]}
            files={svaFiles}
            onAdd={(f) => setSvaFiles((prev) => [...prev, ...f])}
            onRemove={(i) => setSvaFiles((prev) => prev.filter((_, idx) => idx !== i))}
          />

          <SectionLabel>Verification Mode</SectionLabel>
          <SelectInput
            value={mode}
            onChange={setMode}
            options={MODES.map((m) => ({ id: m.id, label: `${m.label} — ${m.desc}` }))}
          />

          <SectionLabel>Solver</SectionLabel>
          <SelectInput
            value={solver}
            onChange={setSolver}
            options={SOLVERS.map((s) => ({ id: s.id, label: s.label }))}
          />

          <SectionLabel>BMC Depth</SectionLabel>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input
              type="range"
              min={5}
              max={100}
              step={5}
              value={depth}
              onChange={(e) => setDepth(Number(e.target.value))}
              style={{ flex: 1, accentColor: "#58a6ff" }}
            />
            <span
              style={{
                fontSize: 12,
                fontFamily: "'JetBrains Mono', monospace",
                color: "#58a6ff",
                minWidth: 28,
                textAlign: "right",
              }}
            >
              {depth}
            </span>
          </div>

          <SectionLabel>Top Module (optional)</SectionLabel>
          <TextInput
            value={topModule}
            onChange={setTopModule}
            placeholder="e.g. fifo"
          />

          <SectionLabel>Timeout (seconds)</SectionLabel>
          <TextInput
            value={String(timeout)}
            onChange={(v) => setTimeout_(Number(v) || 300)}
            placeholder="300"
          />
        </div>

        {/* Run / Reset buttons */}
        <div
          style={{
            padding: "10px 14px",
            borderTop: "1px solid #21262d",
            display: "flex",
            gap: 8,
            flexShrink: 0,
          }}
        >
          <button
            onClick={handleRun}
            disabled={running}
            style={{
              flex: 1,
              padding: "8px 0",
              background: running ? "#21262d" : "#238636",
              color: running ? "#7d8590" : "#fff",
              border: "none",
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 700,
              cursor: running ? "not-allowed" : "pointer",
              transition: "background 0.15s",
            }}
          >
            {running ? "Running..." : "▶  Run Formal"}
          </button>
          <button
            onClick={handleReset}
            style={{
              padding: "8px 10px",
              background: "#21262d",
              color: "#7d8590",
              border: "1px solid #30363d",
              borderRadius: 6,
              fontSize: 12,
              cursor: "pointer",
            }}
            title="Reset"
          >
            ↺
          </button>
        </div>
      </div>

      {/* ── Main results area ── */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

        {/* Status / error bar */}
        {(running || jobStatus || error) && (
          <div
            style={{
              padding: "7px 16px",
              borderBottom: "1px solid #21262d",
              background: "#0d1117",
              display: "flex",
              alignItems: "center",
              gap: 12,
              flexShrink: 0,
            }}
          >
            {running && (
              <span style={{ fontSize: 11, color: "#58a6ff", fontFamily: "'JetBrains Mono', monospace" }}>
                ⏳ {jobPhaseLabel(jobStatus || "queued")}
              </span>
            )}
            {!running && jobStatus && badge && (
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 700,
                  fontFamily: "'JetBrains Mono', monospace",
                  padding: "2px 10px",
                  borderRadius: 4,
                  background: badge.bg,
                  color: badge.color,
                  border: `1px solid ${badge.border}`,
                }}
              >
                {statusIcon(overallStatus)} {overallStatus}
              </span>
            )}
            {!running && jobStatus && !badge && (
              <span style={{ fontSize: 11, color: "#7d8590", fontFamily: "'JetBrains Mono', monospace" }}>
                Status: {jobStatus}
              </span>
            )}
            {jobData?.timing && (
              <span style={{ fontSize: 10, color: "#484f58", fontFamily: "'JetBrains Mono', monospace" }}>
                proving: {jobData.timing.proving_seconds}s &nbsp;|&nbsp; total: {jobData.timing.total_seconds}s
              </span>
            )}
            {error && (
              <span style={{ fontSize: 11, color: "#f85149" }}>✗ {error}</span>
            )}
          </div>
        )}

        {/* Summary stats row */}
        {result && <SummaryBar result={result} depth={depth} />}

        {/* Filter bar (only when we have assertions) */}
        {result?.assertions?.length > 0 && (
          <div
            style={{
              padding: "6px 12px",
              borderBottom: "1px solid #21262d",
              background: "#010409",
              display: "flex",
              alignItems: "center",
              gap: 10,
              flexShrink: 0,
            }}
          >
            <span style={{ fontSize: 10, color: "#7d8590", fontWeight: 700 }}>FILTER</span>
            <SelectInput
              value={filter}
              onChange={setFilter}
              options={FILTER_OPTIONS}
            />
          </div>
        )}

        {/* Property Table */}
        {result?.assertions?.length > 0 ? (
          <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
            <PropertyTable
              result={result}
              solver={jobData?.solver || solver}
              depth={result?.depth_reached || depth}
              filter={filter}
              onOpenTrace={openWaveform}
            />
          </div>
        ) : (
          !running && !jobStatus && (
            <EmptyState />
          )
        )}

        {/* Engine error message (no assertions parsed) */}
        {result && !result.assertions?.length && (
          <div
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              color: "#484f58",
              gap: 8,
            }}
          >
            <div style={{ fontSize: 24 }}>
              {overallStatus === "PASS" ? "✓" : overallStatus === "FAIL" ? "✗" : "⚠"}
            </div>
            <div style={{ fontSize: 13, color: overallStatus === "PASS" ? "#3fb950" : overallStatus === "FAIL" ? "#f85149" : "#d29922" }}>
              {overallStatus} — no per-property breakdown available
            </div>
            {result.error_message && (
              <div style={{ fontSize: 11, color: "#f85149", maxWidth: 500, textAlign: "center" }}>
                {result.error_message}
              </div>
            )}
          </div>
        )}

        {/* Log viewer (collapsible) */}
        {result?.logs && (
          <div style={{ borderTop: "1px solid #21262d", flexShrink: 0 }}>
            <button
              onClick={() => setLogExpanded((v) => !v)}
              style={{
                width: "100%",
                background: "#0d1117",
                border: "none",
                padding: "6px 14px",
                textAlign: "left",
                color: "#7d8590",
                fontSize: 10,
                fontWeight: 700,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 6,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
              }}
            >
              <span>{logExpanded ? "▾" : "▸"}</span> Engine Log
            </button>
            {logExpanded && <LogViewer logs={result.logs} />}
          </div>
        )}
      </div>

      <WaveformModal state={waveformState} onClose={closeWaveform} />
    </div>
  );
}

// ── Empty state ────────────────────────────────────────────────

function EmptyState() {
  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 12,
        color: "#484f58",
        padding: 32,
      }}
    >
      <div style={{ fontSize: 36 }}>🔬</div>
      <div style={{ fontSize: 14, fontWeight: 600, color: "#7d8590" }}>
        Formal Verification — Property Table
      </div>
      <div style={{ fontSize: 12, textAlign: "center", maxWidth: 380, lineHeight: 1.7 }}>
        Upload your design files (.sv / .v) and SVA assertion files, configure
        the engine settings, then click <strong style={{ color: "#3fb950" }}>Run Formal</strong>.
        Results will appear here as a JasperGold-style property table.
      </div>
      <div
        style={{
          marginTop: 8,
          display: "flex",
          flexDirection: "column",
          gap: 4,
          fontSize: 11,
          fontFamily: "'JetBrains Mono', monospace",
          color: "#484f58",
        }}
      >
        <span>✓ Per-property status (Assert / Cover)</span>
        <span>✓ Engine, bound, traces columns</span>
        <span>✓ Collapsible engine log viewer</span>
        <span>✓ Filter by type or result</span>
      </div>
    </div>
  );
}
