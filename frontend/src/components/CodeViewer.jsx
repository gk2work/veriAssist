import { useState, useMemo } from "react";
import { color, font } from "../theme";

const KW = /\b(module|endmodule|class|endclass|function|endfunction|task|endtask|if|else|begin|end|for|foreach|while|return|extends|virtual|static|protected|local|rand|randc|constraint|typedef|enum|struct|logic|bit|int|string|void|input|output|inout|wire|reg|always|initial|assign|property|endproperty|sequence|endsequence|assert|assume|cover|disable|iff|posedge|negedge|interface|endinterface|package|endpackage|import|include|define|ifdef|ifndef|endif|default|clocking|endclocking|throughout|bind|new|super|this|null)\b/g;
const UVM = /\b(uvm_component|uvm_object|uvm_driver|uvm_monitor|uvm_sequencer|uvm_sequence|uvm_agent|uvm_env|uvm_test|uvm_scoreboard|uvm_subscriber|uvm_analysis_port|uvm_analysis_imp|uvm_tlm_analysis_fifo|uvm_config_db|UVM_ACTIVE|UVM_PASSIVE|UVM_ALL_ON|UVM_NONE|UVM_LOW|UVM_MEDIUM|UVM_HIGH|uvm_component_utils|uvm_object_utils|uvm_info|uvm_warning|uvm_error|uvm_fatal|build_phase|connect_phase|run_phase)\b/g;
const SVA = /(\$rose|\$fell|\$stable|\$changed|\$past|\|->|\|=>|##\[\d+:\d+\]|##\d+|\[\*\d*:?\d*\]|\[->\d+\]|\[=\d+\])/g;
const CMT = /(\/\/.*$|\/\*[\s\S]*?\*\/)/gm;
const STR = /("(?:[^"\\]|\\.)*")/g;
const NUM = /\b(\d+(?:'[hbdo][\da-fA-F_]+)?)\b/g;
const MAC = /(`\w+)/g;

function highlightLine(src) {
  return src
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(CMT, '<span style="color:#6a737d;font-style:italic">$&</span>')
    .replace(STR, '<span style="color:#e3b341">$1</span>')
    .replace(MAC, '<span style="color:#d2a8ff">$&</span>')
    .replace(SVA, '<span style="color:#f97583;font-weight:600">$&</span>')
    .replace(UVM, '<span style="color:#79c0ff">$&</span>')
    .replace(KW,  '<span style="color:#ff7b72">$&</span>')
    .replace(NUM, '<span style="color:#a5d6ff">$1</span>');
}

export function SvHighlight({ code, showLineNumbers = true }) {
  const lines = useMemo(() => code.replace(/\n$/, "").split("\n"), [code]);
  const gutterW = String(lines.length).length;

  return (
    <pre
      style={{
        margin: 0,
        padding: "12px 0",
        background: color.bg1,
        borderRadius: "0 0 8px 8px",
        fontSize: 12.5,
        lineHeight: 1.7,
        overflowX: "auto",
        fontFamily: font.mono,
        border: `1px solid ${color.border1}`,
        borderTop: "none",
        color: color.fg1,
      }}
    >
      <code style={{ display: "block" }}>
        {lines.map((line, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              gap: 14,
              padding: "0 14px",
              minWidth: "fit-content",
            }}
          >
            {showLineNumbers && (
              <span
                style={{
                  color: color.fg4,
                  userSelect: "none",
                  textAlign: "right",
                  minWidth: `${gutterW}ch`,
                  flexShrink: 0,
                  fontVariantNumeric: "tabular-nums",
                }}
              >{i + 1}</span>
            )}
            <span
              style={{ flex: 1, whiteSpace: "pre" }}
              dangerouslySetInnerHTML={{ __html: highlightLine(line) || "&nbsp;" }}
            />
          </div>
        ))}
      </code>
    </pre>
  );
}

export function CopyButton({ text }) {
  const [ok, setOk] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text);
        setOk(true);
        setTimeout(() => setOk(false), 1500);
      }}
      style={{
        background: ok ? color.green + "25" : "transparent",
        border: `1px solid ${ok ? color.green + "60" : color.border1}`,
        borderRadius: 4,
        color: ok ? color.green : color.fg2,
        fontSize: 10, padding: "3px 8px",
        fontFamily: font.mono,
        transition: "all 150ms ease",
      }}
      onMouseEnter={(e) => { if (!ok) e.currentTarget.style.borderColor = color.border3; }}
      onMouseLeave={(e) => { if (!ok) e.currentTarget.style.borderColor = color.border1; }}
    >
      {ok ? "✓ Copied" : "Copy"}
    </button>
  );
}

function downloadFile(name, text) {
  const blob = new Blob([text], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function DownloadButton({ text, filename }) {
  return (
    <button
      onClick={() => downloadFile(filename, text)}
      title={`Download ${filename}`}
      style={{
        background: "transparent",
        border: `1px solid ${color.border1}`,
        borderRadius: 4,
        color: color.fg2,
        fontSize: 10, padding: "3px 8px",
        fontFamily: font.mono,
        transition: "all 150ms ease",
      }}
      onMouseEnter={(e) => { e.currentTarget.style.borderColor = color.border3; }}
      onMouseLeave={(e) => { e.currentTarget.style.borderColor = color.border1; }}
    >
      ↓ .{filename.split(".").pop()}
    </button>
  );
}

function extensionFor(lang) {
  const l = (lang || "").toLowerCase();
  if (l === "systemverilog" || l === "sv") return "sv";
  if (l === "verilog" || l === "v") return "v";
  if (l === "vhdl") return "vhd";
  if (l === "bash" || l === "sh") return "sh";
  if (l === "tcl") return "tcl";
  if (l === "python" || l === "py") return "py";
  if (l === "json") return "json";
  if (l === "yaml" || l === "yml") return "yaml";
  if (l === "make" || l === "makefile") return "mk";
  return "txt";
}

export function CodeBlock({ code, lang, filename }) {
  const ext = extensionFor(lang);
  const name = filename || `snippet.${ext}`;
  const lineCount = code.split("\n").length;
  return (
    <div style={{ margin: "10px 0" }}>
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        background: color.bg2,
        padding: "6px 12px",
        borderRadius: "8px 8px 0 0",
        border: `1px solid ${color.border1}`,
        borderBottom: "none",
        gap: 10,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0, fontFamily: font.mono, fontSize: 10 }}>
          <span style={{
            color: color.fg2,
            background: color.bg3,
            border: `1px solid ${color.border1}`,
            padding: "2px 6px", borderRadius: 3,
            textTransform: "lowercase", letterSpacing: 0.3,
          }}>
            {lang || "systemverilog"}
          </span>
          <span style={{ color: color.fg3, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {name}
          </span>
          <span style={{ color: color.fg4 }}>· {lineCount} {lineCount === 1 ? "line" : "lines"}</span>
        </div>
        <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
          <DownloadButton text={code} filename={name} />
          <CopyButton text={code} />
        </div>
      </div>
      <SvHighlight code={code} />
    </div>
  );
}
