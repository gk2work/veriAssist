import { useRef, useEffect } from "react";
import { MODES, QUICK_PROMPTS } from "../config/constants";
import { CodeBlock } from "./CodeViewer";
import { color, font, brandGradient, modeAccent } from "../theme";

function parseMsg(text) {
  const parts = [];
  const re = /```(\w*)\n([\s\S]*?)```/g;
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push({ type: "text", content: text.slice(last, m.index) });
    parts.push({ type: "code", lang: m[1] || "systemverilog", content: m[2].trim() });
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push({ type: "text", content: text.slice(last) });
  return parts;
}

function fmt(text) {
  // Bold (**text**), then inline `code`. Order matters: bold first so its
  // markers don't eat backticks inside the bold span.
  const parts = [];
  const bold = /(\*\*.*?\*\*)/g;
  text.split(bold).forEach((chunk, i) => {
    if (chunk.startsWith("**") && chunk.endsWith("**")) {
      parts.push(<strong key={`b${i}`} style={{ color: color.fg1, fontWeight: 600 }}>{chunk.slice(2, -2)}</strong>);
    } else {
      const sub = chunk.split(/(`[^`]+`)/g);
      sub.forEach((s, j) => {
        if (s.startsWith("`") && s.endsWith("`") && s.length > 1) {
          parts.push(<code key={`c${i}-${j}`} className="va-inline-code">{s.slice(1, -1)}</code>);
        } else {
          parts.push(<span key={`t${i}-${j}`}>{s}</span>);
        }
      });
    }
  });
  return parts;
}

function Avatar({ role }) {
  const isUser = role === "user";
  return (
    <div
      style={{
        width: 28, height: 28, borderRadius: 7, flexShrink: 0,
        background: isUser ? color.bg3 : brandGradient,
        border: isUser ? `1px solid ${color.border2}` : "none",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 11, fontWeight: 700,
        color: isUser ? color.fg1 : "#fff",
        fontFamily: font.mono,
      }}
    >
      {isUser ? "U" : "V"}
    </div>
  );
}

export default function ChatPanel({ msgs, loading, mode, model, send, stop, clear }) {
  const endRef = useRef(null);
  const inputRef = useRef(null);
  const textRef = useRef("");

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  const modeInfo = MODES.find((m) => m.id === mode);
  const accent = modeAccent[mode]?.color || color.blue;

  const handleSend = () => {
    const val = textRef.current;
    if (!val.trim()) return;
    send(val);
    if (inputRef.current) { inputRef.current.value = ""; inputRef.current.style.height = "22px"; }
    textRef.current = "";
  };

  const onKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const setPrompt = (p) => {
    if (!inputRef.current) return;
    inputRef.current.value = p;
    inputRef.current.style.height = "22px";
    inputRef.current.style.height = inputRef.current.scrollHeight + "px";
    textRef.current = p;
    inputRef.current.focus();
  };

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, background: color.bg0 }}>
      {/* Action bar — sits under the workbench header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "6px 18px", height: 32, flexShrink: 0,
        borderBottom: `1px solid ${color.border1}`, background: color.bg1,
      }}>
        <span style={{ fontFamily: font.mono, fontSize: 10, color: color.fg3 }}>
          {msgs.length === 0 ? "new conversation" : `${msgs.length} message${msgs.length === 1 ? "" : "s"}`}
        </span>
        <div style={{ display: "flex", gap: 6 }}>
          {loading && (
            <button
              onClick={stop}
              style={{
                background: color.red + "18", border: `1px solid ${color.red}40`,
                borderRadius: 6, color: color.red, fontSize: 10, padding: "4px 10px",
                fontFamily: font.mono,
              }}
            >Stop</button>
          )}
          <button
            onClick={clear}
            disabled={msgs.length === 0}
            style={{
              background: color.bg2, border: `1px solid ${color.border1}`,
              borderRadius: 6, color: msgs.length === 0 ? color.fg4 : color.fg2,
              fontSize: 10, padding: "4px 10px",
              fontFamily: font.mono,
              cursor: msgs.length === 0 ? "not-allowed" : "pointer",
            }}
          >Clear</button>
        </div>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", padding: "20px 0 0" }}>
        {msgs.length === 0 && (
          <div style={{
            display: "flex", flexDirection: "column", alignItems: "center",
            justifyContent: "center", height: "100%", gap: 20,
            animation: "fadeIn .4s ease", padding: "0 24px",
          }}>
            <div style={{
              width: 64, height: 64, borderRadius: 16,
              background: `${accent}14`,
              border: `1px solid ${accent}30`,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 28,
              boxShadow: `0 0 0 6px ${accent}08`,
            }}>{modeInfo.icon}</div>
            <div style={{ textAlign: "center", maxWidth: 480 }}>
              <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 4, color: color.fg1 }}>
                {modeInfo.label}
              </div>
              <div style={{ fontSize: 12.5, color: color.fg3, lineHeight: 1.55 }}>
                {modeInfo.desc}. Powered by quantized local LLMs — 100% on-device, zero API cost.
              </div>
            </div>

            <div style={{ width: "100%", maxWidth: 640, marginTop: 4 }}>
              <div style={{
                fontSize: 10, fontFamily: font.mono, color: color.fg3,
                textAlign: "center", marginBottom: 10, letterSpacing: 0.5, textTransform: "uppercase",
              }}>
                Try one of these
              </div>
              <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
                gap: 8,
              }}>
                {(QUICK_PROMPTS[mode] || []).map((p, i) => (
                  <button
                    key={i}
                    onClick={() => setPrompt(p)}
                    style={{
                      background: color.bg1,
                      border: `1px solid ${color.border1}`,
                      borderRadius: 8,
                      color: color.fg2,
                      fontSize: 11.5, padding: "10px 12px",
                      textAlign: "left", lineHeight: 1.4,
                      transition: "all 140ms ease",
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.borderColor = accent + "60";
                      e.currentTarget.style.background = color.bg2;
                      e.currentTarget.style.color = color.fg1;
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = color.border1;
                      e.currentTarget.style.background = color.bg1;
                      e.currentTarget.style.color = color.fg2;
                    }}
                  >{p}</button>
                ))}
              </div>
            </div>
          </div>
        )}

        <div style={{ maxWidth: 920, margin: "0 auto", padding: "0 24px" }}>
          {msgs.map((msg, idx) => {
            const isUser = msg.role === "user";
            return (
              <div
                key={idx}
                style={{
                  display: "flex", gap: 12, marginBottom: 18,
                  animation: "fadeIn .25s ease",
                  flexDirection: isUser ? "row-reverse" : "row",
                }}
              >
                <Avatar role={msg.role} />
                <div style={{
                  maxWidth: "82%",
                  background: isUser ? color.bg2 : "transparent",
                  border: isUser ? `1px solid ${color.border1}` : "none",
                  borderRadius: 10,
                  padding: isUser ? "10px 14px" : "4px 0 0",
                  fontSize: 13, lineHeight: 1.65, color: color.fg1,
                }}>
                  {parseMsg(msg.content).map((part, j) =>
                    part.type === "code"
                      ? <CodeBlock key={j} code={part.content} lang={part.lang} />
                      : <div key={j} style={{ whiteSpace: "pre-wrap" }}>{fmt(part.content)}</div>
                  )}
                </div>
              </div>
            );
          })}

          {loading && (
            <div style={{ display: "flex", gap: 12, marginBottom: 18 }}>
              <Avatar role="assistant" />
              <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 0", color: accent, fontSize: 12 }}>
                <span style={{ animation: "pulse 1.2s infinite" }}>{"●"}</span>
                <span style={{ fontFamily: font.mono, fontSize: 11 }}>generating…</span>
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>
      </div>

      {/* Composer */}
      <div style={{
        padding: "12px 24px 16px",
        background: color.bg1,
        borderTop: `1px solid ${color.border1}`,
      }}>
        <div style={{
          maxWidth: 920, margin: "0 auto",
          display: "flex", alignItems: "flex-end", gap: 8,
          background: color.bg2,
          border: `1px solid ${color.border1}`,
          borderRadius: 12, padding: "10px 12px",
          transition: "border-color 120ms ease",
        }}
        onFocusCapture={(e) => { e.currentTarget.style.borderColor = accent + "60"; }}
        onBlurCapture={(e) => { e.currentTarget.style.borderColor = color.border1; }}
        >
          <textarea
            ref={inputRef}
            onChange={(e) => { textRef.current = e.target.value; }}
            onKeyDown={onKey}
            placeholder={`Ask VeriAssist — ${modeInfo.label} mode`}
            rows={1}
            style={{
              flex: 1, background: "transparent", border: "none",
              color: color.fg1, fontSize: 13, resize: "none", outline: "none",
              minHeight: 22, maxHeight: 200, lineHeight: 1.5,
            }}
            onInput={(e) => {
              e.target.style.height = "22px";
              e.target.style.height = e.target.scrollHeight + "px";
            }}
          />
          <button
            onClick={handleSend}
            disabled={loading}
            aria-label="Send"
            style={{
              background: loading ? color.bg3 : accent,
              border: "none", borderRadius: 8,
              width: 32, height: 32,
              display: "flex", alignItems: "center", justifyContent: "center",
              cursor: loading ? "not-allowed" : "pointer",
              fontSize: 14, fontWeight: 700,
              color: loading ? color.fg3 : "#08111f",
              flexShrink: 0, transition: "all .15s",
            }}
          >{"↑"}</button>
        </div>
        <div style={{
          maxWidth: 920, margin: "8px auto 0",
          display: "flex", justifyContent: "space-between",
          fontFamily: font.mono, fontSize: 9.5, color: color.fg3,
        }}>
          <span>↵ send · ⇧↵ newline</span>
          <span>{modeInfo.icon} {modeInfo.label} · {"\u{1F512}"} local · $0</span>
        </div>
      </div>
    </div>
  );
}
