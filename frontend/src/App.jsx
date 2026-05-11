import { useState } from "react";
import Sidebar from "./components/Sidebar";
import ChatPanel from "./components/ChatPanel";
import FormalPanel from "./components/FormalPanel";
import FVPanel from "./components/FVPanel";
import GeneratePanel from "./components/GeneratePanel";
import CoveragePanel from "./components/CoveragePanel";
import { useVeriAssist } from "./hooks/useVeriAssist";
import { MODES } from "./config/constants";
import { color, font, modeAccent } from "./theme";

const SPECIAL_MODES = {
  formal:   { badge: "SVA + SymbiYosys",   Panel: FormalPanel },
  generate: { badge: "UVM Testbench",      Panel: GeneratePanel },
  debug:    { badge: "Coverage Advisor",   Panel: CoveragePanel },
  fv:       { badge: "sby + Property Table", Panel: FVPanel },
};

function ActivityBar({ mode, setMode, sidebarOpen, setSidebarOpen }) {
  return (
    <div
      style={{
        width: 52,
        background: color.bg0,
        borderRight: `1px solid ${color.border1}`,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        paddingTop: 10,
        gap: 4,
        flexShrink: 0,
      }}
    >
      <button
        onClick={() => setSidebarOpen(!sidebarOpen)}
        title={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
        aria-label="Toggle sidebar"
        style={{
          width: 36, height: 36, borderRadius: 8,
          display: "flex", alignItems: "center", justifyContent: "center",
          color: color.fg3, fontSize: 16,
        }}
        onMouseEnter={(e) => { e.currentTarget.style.background = color.bg3; e.currentTarget.style.color = color.fg1; }}
        onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = color.fg3; }}
      >
        {"☰"}
      </button>

      <div style={{ width: 28, height: 1, background: color.border1, margin: "8px 0" }} />

      {MODES.map((m) => {
        const active = mode === m.id;
        const accent = modeAccent[m.id]?.color || color.blue;
        return (
          <button
            key={m.id}
            onClick={() => setMode(m.id)}
            title={`${m.label} — ${m.desc}`}
            aria-label={m.label}
            aria-pressed={active}
            style={{
              position: "relative",
              width: 36, height: 36, borderRadius: 8,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 17,
              color: active ? color.fg1 : color.fg3,
              background: active ? color.bg3 : "transparent",
              transition: "background 120ms ease, color 120ms ease",
            }}
            onMouseEnter={(e) => { if (!active) { e.currentTarget.style.background = color.bg2; e.currentTarget.style.color = color.fg1; } }}
            onMouseLeave={(e) => { if (!active) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = color.fg3; } }}
          >
            {active && (
              <span style={{
                position: "absolute", left: -10, top: 8, bottom: 8,
                width: 2, borderRadius: 2, background: accent,
              }} />
            )}
            <span>{m.icon}</span>
          </button>
        );
      })}
    </div>
  );
}

function WorkbenchHeader({ mode, model, badge }) {
  const info = MODES.find((m) => m.id === mode);
  const accent = modeAccent[mode]?.color || color.blue;
  if (!info) return null;
  return (
    <div
      style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 18px",
        background: color.bg1,
        borderBottom: `1px solid ${color.border1}`,
        height: 44, flexShrink: 0,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
        <span style={{ fontSize: 16 }}>{info.icon}</span>
        <span style={{ fontSize: 13, fontWeight: 600, color: color.fg1 }}>{info.label}</span>
        <span style={{ width: 1, height: 14, background: color.border1, margin: "0 4px" }} />
        <span style={{ fontSize: 11, color: color.fg3 }}>{info.desc}</span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {model && (
          <span style={{
            fontFamily: font.mono, fontSize: 10, color: color.fg2,
            background: color.bg2, border: `1px solid ${color.border1}`,
            padding: "3px 8px", borderRadius: 4,
          }}>
            {(model || "").split(":")[0]}
          </span>
        )}
        {badge && (
          <span style={{
            fontSize: 9, fontWeight: 700, letterSpacing: 0.4,
            background: accent + "20", color: accent,
            border: `1px solid ${accent}40`,
            padding: "3px 8px", borderRadius: 4,
            textTransform: "uppercase",
          }}>
            {badge}
          </span>
        )}
      </div>
    </div>
  );
}

function StatusBar({ status, model, mode }) {
  const ok = status.ollama === "connected";
  const checking = status.ollama === "checking";
  const dot = ok ? color.green : checking ? color.yellow : color.red;
  const sbyOk = status.sby === "available";
  return (
    <div
      style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        height: 22, padding: "0 12px", flexShrink: 0,
        background: color.bg1,
        borderTop: `1px solid ${color.border1}`,
        fontFamily: font.mono, fontSize: 10, color: color.fg3,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
          <span style={{
            width: 7, height: 7, borderRadius: "50%", background: dot,
            animation: checking ? "pulse 1.5s infinite" : "none",
          }} />
          ollama · {ok ? "connected" : checking ? "checking" : "disconnected"}
        </span>
        <span>sby · <span style={{ color: sbyOk ? color.green : color.red }}>{status.sby || "?"}</span></span>
        <span>lowering · <span style={{ color: color.green }}>custom engine</span></span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <span>{modeAccent[mode]?.label || mode}</span>
        <span>{(model || "").split(":")[0] || "no model"}</span>
        <span>{"\u{1F512}"} local · $0</span>
      </div>
    </div>
  );
}

export default function App() {
  const [sidebar, setSidebar] = useState(true);
  const va = useVeriAssist();
  const special = SPECIAL_MODES[va.mode];

  return (
    <div style={{
      display: "flex", flexDirection: "column",
      height: "100vh",
      background: color.bg0, color: color.fg1, fontFamily: font.sans,
    }}>
      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
        <ActivityBar
          mode={va.mode}
          setMode={va.setMode}
          sidebarOpen={sidebar}
          setSidebarOpen={setSidebar}
        />
        <Sidebar
          mode={va.mode}
          setMode={va.setMode}
          model={va.model}
          setModel={va.setModel}
          models={va.models}
          status={va.status}
          temp={va.temp}
          setTemp={va.setTemp}
          open={sidebar}
        />
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          <WorkbenchHeader mode={va.mode} model={va.model} badge={special?.badge} />
          <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
            {special ? (
              <special.Panel model={va.model} />
            ) : (
              <ChatPanel
                msgs={va.msgs}
                loading={va.loading}
                mode={va.mode}
                model={va.model}
                send={va.send}
                stop={va.stop}
                clear={va.clear}
              />
            )}
          </div>
        </div>
      </div>
      <StatusBar status={va.status} model={va.model} mode={va.mode} />
    </div>
  );
}
