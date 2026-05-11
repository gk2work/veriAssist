import { useState, useEffect, useCallback, useRef } from "react";
import { API_BASE } from "../config/constants";

export function useVeriAssist() {
  const [msgs, setMsgs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [model, setModel] = useState("");
  const [models, setModels] = useState([]);
  const [status, setStatus] = useState({ ollama: "checking", sva2sby: "?", sby: "?" });
  const [mode, setMode] = useState("chat");
  const [temp, setTemp] = useState(0.3);
  const abortRef = useRef(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/health`)
      .then(r => r.json())
      .then(d => { setStatus(d); if (d.default_model) setModel(d.default_model); })
      .catch(() => setStatus({ ollama: "disconnected", sva2sby: "?", sby: "?" }));
    fetch(`${API_BASE}/api/models`)
      .then(r => r.json())
      .then(d => setModels(d.models || []))
      .catch(() => {});
  }, []);

  const send = useCallback(async (input) => {
    if (!input.trim() || loading) return;
    const userMsg = { role: "user", content: input.trim() };
    const history = [...msgs, userMsg];
    setMsgs(history);
    setLoading(true);
    let full = "";
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const resp = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          message: userMsg.content,
          history: msgs.map(m => ({ role: m.role, content: m.content })),
          mode, model: model || undefined, temperature: temp, max_tokens: 4096,
        }),
      });
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        for (const line of decoder.decode(value).split("\n")) {
          if (!line.startsWith("data: ")) continue;
          try {
            const d = JSON.parse(line.slice(6));
            if (d.token) { full += d.token; setMsgs([...history, { role: "assistant", content: full }]); }
          } catch {}
        }
      }
      setMsgs([...history, { role: "assistant", content: full }]);
    } catch (err) {
      if (err.name === "AbortError") {
        setMsgs([...history, { role: "assistant", content: full + "\n\n*[Stopped]*" }]);
      } else {
        setMsgs([...history, { role: "assistant", content:
          status.ollama === "disconnected"
            ? "**Cannot connect to backend.** Make sure both are running:\n```bash\n# Terminal 1\ncd backend && uvicorn app.main:app --reload --port 8000\n\n# Terminal 2\nollama serve\n```"
            : `**Error:** ${err.message}` }]);
      }
    }
    setLoading(false);
  }, [msgs, mode, model, temp, loading, status]);

  const stop = useCallback(() => { if (abortRef.current) abortRef.current.abort(); }, []);
  const clear = useCallback(() => setMsgs([]), []);

  return { msgs, loading, model, setModel, models, status, mode, setMode, temp, setTemp, send, stop, clear };
}
