// Shared design tokens. Mirrors the CSS variables in index.css so JSX
// inline styles can reference the same palette and spacing scale.
// Panels can migrate to these incrementally.

export const color = {
  bg0: "#0a0c10",
  bg1: "#0d1117",
  bg2: "#11161d",
  bg3: "#161b22",
  bg4: "#1c232c",

  border1: "#1f2630",
  border2: "#2a313c",
  border3: "#3b434f",

  fg1: "#e6edf3",
  fg2: "#adb6c0",
  fg3: "#7d8590",
  fg4: "#565f6b",

  blue: "#58a6ff",
  violet: "#bc8cff",
  green: "#3fb950",
  yellow: "#d29922",
  red: "#f85149",
  cyan: "#39c5cf",
};

export const brandGradient = "linear-gradient(135deg, #58a6ff 0%, #bc8cff 100%)";

export const font = {
  sans: "'Inter', 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  mono: "'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, monospace",
};

export const radius = { sm: 4, md: 6, lg: 8, xl: 10 };
export const space = { 1: 4, 2: 8, 3: 12, 4: 16, 5: 20, 6: 24 };

export const elev = {
  1: "0 1px 2px rgba(0,0,0,0.35)",
  2: "0 4px 12px rgba(0,0,0,0.45)",
  3: "0 12px 32px rgba(0,0,0,0.55)",
};

// Mode-specific accent palette — used for activity bar indicator,
// badges, and panel headers. Keys must match MODES[].id in constants.js.
export const modeAccent = {
  chat:     { color: color.blue,   label: "Chat" },
  docs:     { color: color.cyan,   label: "Docs" },
  generate: { color: color.violet, label: "UVM Generate" },
  sva:      { color: color.yellow, label: "SVA" },
  formal:   { color: color.green,  label: "Formal" },
  debug:    { color: color.red,    label: "Debug" },
  fv:       { color: "#9d6cff",    label: "Formal Verification" },
};
