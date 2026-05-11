import { useState } from "react";
import { MODES } from "../config/constants";
import { color, font, brandGradient, modeAccent } from "../theme";

function SectionHeader({ label, hint, open, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        width: "100%",
        padding: "10px 14px 6px",
        color: color.fg3,
        fontSize: 10, fontWeight: 700, letterSpacing: 0.8,
        textTransform: "uppercase",
      }}
    >
      <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{
          fontSize: 9,
          transform: open ? "rotate(90deg)" : "rotate(0deg)",
          transition: "transform 150ms ease",
          display: "inline-block",
        }}>▶</span>
        {label}
      </span>
      {hint && <span style={{ fontFamily: font.mono, fontSize: 9, textTransform: "none", letterSpacing: 0, color: color.fg4 }}>{hint}</span>}
    </button>
  );
}

function ModeRow({ m, active, onClick }) {
  const accent = modeAccent[m.id]?.color || color.blue;
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      style={{
        position: "relative",
        display: "flex", alignItems: "center", gap: 10,
        width: "100%",
        padding: "8px 12px",
        background: active ? color.bg3 : "transparent",
        color: active ? color.fg1 : color.fg2,
        borderRadius: 6,
        textAlign: "left",
        marginBottom: 1,
        transition: "background 120ms ease, color 120ms ease",
      }}
      onMouseEnter={(e) => { if (!active) e.currentTarget.style.background = color.bg2; }}
      onMouseLeave={(e) => { if (!active) e.currentTarget.style.background = "transparent"; }}
    >
      {active && (
        <span style={{
          position: "absolute", left: 0, top: 8, bottom: 8,
          width: 2, borderRadius: 2, background: accent,
        }} />
      )}
      <span style={{ fontSize: 14, width: 18, textAlign: "center" }}>{m.icon}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12.5, fontWeight: active ? 600 : 500 }}>{m.label}</div>
        <div style={{ fontSize: 10.5, color: color.fg3, marginTop: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {m.desc}
        </div>
      </div>
      {m.id === "formal" && (
        <span style={{
          fontSize: 8, fontWeight: 700,
          padding: "2px 6px", borderRadius: 3,
          background: color.green + "25", color: color.green,
        }}>NEW</span>
      )}
    </button>
  );
}

export default function Sidebar({
  mode, setMode,
  model, setModel, models,
  status, temp, setTemp,
  open,
}) {
  const [modesOpen, setModesOpen] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(true);

  const tempLabel = temp <= 0.2 ? "Precise" : temp <= 0.5 ? "Balanced" : "Creative";
  const tempColor = temp <= 0.2 ? color.green : temp <= 0.5 ? color.blue : color.violet;

  return (
    <aside
      style={{
        width: open ? 264 : 0,
        overflow: "hidden",
        transition: "width 200ms ease",
        background: color.bg1,
        borderRight: `1px solid ${color.border1}`,
        display: "flex",
        flexDirection: "column",
        flexShrink: 0,
      }}
    >
      {/* Brand */}
      <div style={{ padding: "16px 14px 14px", borderBottom: `1px solid ${color.border1}` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8,
            background: brandGradient,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 15, fontWeight: 800, color: "#fff",
            boxShadow: "0 1px 0 rgba(255,255,255,0.08) inset",
          }}>V</div>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 700, fontSize: 14, letterSpacing: -0.2, color: color.fg1 }}>
              VeriAssist
            </div>
            <div style={{ fontFamily: font.mono, fontSize: 9.5, color: color.fg3, marginTop: 1 }}>
              v2.0 · phases 1–7
            </div>
          </div>
        </div>
      </div>

      {/* Modes */}
      <SectionHeader
        label="Mode"
        hint={`${MODES.length} total`}
        open={modesOpen}
        onClick={() => setModesOpen(!modesOpen)}
      />
      {modesOpen && (
        <div style={{ padding: "0 8px 8px", flex: 1, overflowY: "auto", minHeight: 0 }}>
          {MODES.map((m) => (
            <ModeRow key={m.id} m={m} active={mode === m.id} onClick={() => setMode(m.id)} />
          ))}
        </div>
      )}

      {/* Settings */}
      <div style={{ borderTop: `1px solid ${color.border1}` }}>
        <SectionHeader
          label="Settings"
          open={settingsOpen}
          onClick={() => setSettingsOpen(!settingsOpen)}
        />
        {settingsOpen && (
          <div style={{ padding: "0 14px 14px", display: "flex", flexDirection: "column", gap: 12 }}>
            {/* Model */}
            <div>
              <label style={{
                display: "block",
                fontSize: 10, color: color.fg3, marginBottom: 4,
                fontFamily: font.mono, letterSpacing: 0.3,
              }}>
                model
              </label>
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                style={{
                  width: "100%",
                  background: color.bg2,
                  border: `1px solid ${color.border1}`,
                  borderRadius: 6,
                  color: color.fg1,
                  padding: "6px 8px",
                  fontSize: 11,
                  fontFamily: font.mono,
                  cursor: "pointer",
                  outline: "none",
                }}
              >
                {models.length === 0 && <option value="">No models found</option>}
                {models.map((m) => (
                  <option key={m.name} value={m.name}>
                    {m.name} ({m.size || m.parameter_size})
                  </option>
                ))}
              </select>
            </div>

            {/* Temperature */}
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
                <span style={{ fontSize: 10, color: color.fg3, fontFamily: font.mono, letterSpacing: 0.3 }}>
                  temperature
                </span>
                <span style={{
                  fontSize: 10, fontFamily: font.mono, color: tempColor, fontWeight: 600,
                }}>
                  {temp.toFixed(1)} · {tempLabel}
                </span>
              </div>
              <input
                type="range"
                min="0" max="1" step="0.1"
                value={temp}
                onChange={(e) => setTemp(parseFloat(e.target.value))}
                style={{ width: "100%", accentColor: tempColor, height: 4 }}
              />
              <div style={{
                display: "flex", justifyContent: "space-between",
                fontFamily: font.mono, fontSize: 8.5, color: color.fg4, marginTop: 2,
              }}>
                <span>0.0</span><span>0.5</span><span>1.0</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
