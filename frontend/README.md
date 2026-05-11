# VeriAssist Frontend

React + Vite UI for the VeriAssist VLSI design assistant. Features a VS Code-style layout with a permanent activity bar, collapsible sidebar, and mode-specific panels.

## Setup

```bash
npm install
npm run dev       # http://localhost:5173
npm run build     # production build → dist/
```

## Layout

```
┌──────┬──────────────┬────────────────────────────────┐
│      │              │                                │
│  A   │   Sidebar    │         Main Panel             │
│  c   │              │                                │
│  t   │  Mode nav    │  ChatPanel / FormalPanel /     │
│  i   │  Model pick  │  GeneratePanel / FVPanel /     │
│  v   │  Temp slider │  CoveragePanel                 │
│  i   │              │                                │
│  t   │              │                                │
│  y   │              │                                │
│  B   │              │                                │
│  a   │              │                                │
│  r   │              │                                │
├──────┴──────────────┴────────────────────────────────┤
│                    Status Bar                        │
└──────────────────────────────────────────────────────┘
```

## Components

| Component | Description |
|-----------|-------------|
| `App.jsx` | Root layout — ActivityBar, Sidebar, WorkbenchHeader, StatusBar |
| `Sidebar.jsx` | Collapsible panel with mode list, model selector, temperature |
| `ChatPanel.jsx` | Streaming markdown chat (chat / docs / sva / debug modes) |
| `FormalPanel.jsx` | SVA editor + SymbiYosys job runner + result viewer |
| `FVPanel.jsx` | File-upload formal verification with property table |
| `GeneratePanel.jsx` | UVM testbench generator with interface parser |
| `CoveragePanel.jsx` | DUT analysis, covergroup generation, sequence advisor |
| `CodeViewer.jsx` | Syntax-highlighted code display with copy button |

## State

All API state lives in `hooks/useVeriAssist.js`:
- Fetches available models and health on mount
- Handles streaming SSE responses from `/api/chat`
- Exposes `send`, `stop`, `clear` actions

## Theme

Design tokens are in `src/theme.js` — colors, fonts, spacing, and per-mode accent colors. All components reference these tokens for consistency.

## Config

Backend URL defaults to `http://localhost:8000`. Change `API_BASE` in `src/config/constants.js` to point elsewhere.
