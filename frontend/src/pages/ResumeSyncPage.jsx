import { useState, useEffect, useCallback } from "react";
import * as api from "../api/client";
import { useProvider } from "../context/ProviderContext";
import ChatHistoryPanel from "../components/ChatHistoryPanel";
import TruncationBanner from "../components/TruncationBanner";
import UpgradeBanner from "../components/UpgradeBanner";

const LEVEL_COLOR = {
  Expert: "bg-purple-100 text-purple-700",
  Advanced: "bg-blue-100 text-blue-700",
  Intermediate: "bg-emerald-100 text-emerald-700",
  Beginner: "bg-gray-100 text-gray-600",
};

// Resume Sync: (1) a tool-by-tool experience breakdown so you can state your years/clients per
// tool without hesitating, and (2) a vendor screening-call simulator against a pasted JD, so
// you walk into that call already knowing what a vendor will ask and how to answer it in a way
// that actually satisfies them. Both sides save their generations as reopenable history - the
// vendor-prep side additionally dedups by JD content on the backend, so pasting a JD you already
// prepped for reuses the saved answers instead of spending tokens again.
export default function ResumeSyncPage() {
  const [tab, setTab] = useState("tools");

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <h1 className="text-xl font-medium text-gray-900 mb-1">🎯 Resume Sync</h1>
      <p className="text-sm text-gray-500 mb-4">
        Know your own resume cold — a tool-by-tool experience breakdown, plus a vendor screening
        call simulator built from a real job description.
      </p>

      <div className="flex gap-2 mb-4 border-b border-gray-200">
        {[
          { key: "tools", label: "🧰 Tool Sync" },
          { key: "vendor", label: "📞 Vendor JD Prep" },
        ].map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px transition ${
              tab === t.key ? "border-accent text-accent" : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "tools" ? <ToolSyncTab /> : <VendorPrepTab />}
    </div>
  );
}

function ToolSyncTab() {
  const { provider } = useProvider();
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [tools, setTools] = useState(null);
  const [truncated, setTruncated] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [capHit, setCapHit] = useState(false);

  const refreshSessions = useCallback(() => {
    api.listSessions("resume_sync_tools").then(setSessions).catch(() => {});
  }, []);

  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  async function handleSync() {
    setBusy(true);
    setError("");
    setCapHit(false);
    try {
      const data = await api.generateToolBreakdown(provider);
      setTools(data.tools);
      setTruncated(data.truncated);

      const created = await api.createSession("resume_sync_tools", "Resume sync");
      setActiveSessionId(created.id);
      await api.appendSessionMessage(created.id, "Resume sync", data);
      refreshSessions();
    } catch (err) {
      if (err.status === 402) {
        setCapHit(true);
      } else {
        setError(err.message || "Couldn't sync your resume — try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleSelectSession(sessionId) {
    setError("");
    try {
      const session = await api.getSession(sessionId);
      setActiveSessionId(sessionId);
      const last = session.messages[session.messages.length - 1];
      setTools(last ? last.response.tools : null);
      setTruncated(last ? last.response.truncated : false);
    } catch (err) {
      setError(err.message || "Couldn't load that sync.");
    }
  }

  async function handleDeleteSession(sessionId) {
    try {
      await api.deleteSession(sessionId);
      if (sessionId === activeSessionId) {
        setActiveSessionId(null);
        setTools(null);
      }
      refreshSessions();
    } catch (err) {
      setError(err.message || "Couldn't delete that chat — try again.");
    }
  }

  async function handleRenameSession(sessionId, title) {
    try {
      await api.renameSession(sessionId, title);
      refreshSessions();
    } catch (err) {
      setError(err.message || "Couldn't rename that chat — try again.");
    }
  }

  async function handleSearch(query) {
    try {
      const results = query.trim()
        ? await api.searchSessions("resume_sync_tools", query.trim())
        : await api.listSessions("resume_sync_tools");
      setSessions(results);
    } catch {
      // ignore
    }
  }

  return (
    <div className="flex -mx-6">
      <ChatHistoryPanel
        sessions={sessions}
        activeSessionId={activeSessionId}
        onNewChat={() => { setActiveSessionId(null); setTools(null); }}
        onSelect={handleSelectSession}
        onDelete={handleDeleteSession}
        onRename={handleRenameSession}
        onSearch={handleSearch}
      />
      <div className="flex-1 px-6">
        <button
          type="button"
          onClick={handleSync}
          disabled={busy}
          className="bg-accent text-white rounded-lg px-4 py-2.5 text-sm font-medium hover:brightness-110 transition disabled:opacity-60 mb-4"
        >
          {busy ? "🔄 Reading your entire resume..." : "🔄 Sync my resume"}
        </button>

        {capHit && <UpgradeBanner message="You've hit today's free resume-sync limit." />}
        {error && <p className="text-sm text-red-600 mb-4">{error}</p>}
        {truncated && <TruncationBanner />}

        {!tools ? (
          <p className="text-sm text-gray-400">
            Click "Sync my resume" to get a tool-by-tool breakdown of your experience — or pick a
            past sync from the list on the left.
          </p>
        ) : (
          <div className="space-y-3">
            {tools.map((t, i) => (
              <ToolCard key={i} tool={t} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// Collapsed by default - a resume with 15-20+ tools each showing 2-3 sentences per client got
// very long very fast as an always-expanded list. Click the tool row to expand just that one.
function ToolCard({ tool }) {
  const [open, setOpen] = useState(false);
  const usages = tool.usages && tool.usages.length ? tool.usages : (tool.clients || []).map((c) => ({ client: c, detail: "" }));

  return (
    <div className="border border-gray-200 rounded-xl bg-white overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 flex-wrap px-4 py-3 text-left hover:bg-gray-50 transition"
      >
        <span className="text-gray-400 text-xs shrink-0">{open ? "▼" : "▶"}</span>
        <p className="text-sm font-semibold text-gray-900">{tool.tool}</p>
        <span className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${LEVEL_COLOR[tool.level] || "bg-gray-100 text-gray-600"}`}>
          {tool.level}
        </span>
        <span className="text-xs text-gray-400">{tool.experience} total</span>
        <span className="text-xs text-gray-400 ml-auto">
          {usages.length} client{usages.length !== 1 ? "s" : ""}
        </span>
      </button>
      {open && (
        <div className="px-4 pb-4">
          {usages.length === 0 ? (
            <p className="text-xs text-gray-400">No specific client tied to this in the resume.</p>
          ) : (
            <div className="space-y-3">
              {usages.map((u, idx) => (
                <div key={idx} className="border-l-2 border-gray-200 pl-3">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <p className="text-sm font-medium text-gray-800">{u.client}</p>
                    {u.inferred && (
                      <span
                        className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700"
                        title="Reconstructed from the role's surrounding context, not a direct line in the resume - confirm it matches your actual memory before repeating it on a call."
                      >
                        🧩 inferred — verify
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-gray-600 leading-relaxed">
                    {u.detail || <span className="italic text-gray-400">Listed for this client, no further detail in the resume.</span>}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const CATEGORY_STYLE = {
  "Tool Depth": { emoji: "🛠️", color: "#2196F3" },
  "Project Scope": { emoji: "📦", color: "#9C27B0" },
  "Availability": { emoji: "🗓️", color: "#4CAF50" },
  "Rate": { emoji: "💰", color: "#FF9800" },
  "Work Authorization": { emoji: "🪪", color: "#607D8B" },
  "Relocation": { emoji: "✈️", color: "#00838F" },
  "Gaps": { emoji: "⚠️", color: "#FF5722" },
  "Motivation": { emoji: "🎯", color: "#3F51B5" },
};

function VendorPrepTab() {
  const { provider } = useProvider();
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [jdText, setJdText] = useState("");
  const [items, setItems] = useState(null);
  const [truncated, setTruncated] = useState(false);
  const [fromCache, setFromCache] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [capHit, setCapHit] = useState(false);

  const refreshSessions = useCallback(() => {
    api.listSessions("resume_sync_qa").then(setSessions).catch(() => {});
  }, []);

  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  async function handleGenerate() {
    if (!jdText.trim()) {
      setError("Please paste a job description first.");
      return;
    }
    setError("");
    setCapHit(false);
    setBusy(true);
    try {
      const data = await api.generateVendorQa({ jdText, provider, numQuestions: 8 });
      setItems(data.items);
      setTruncated(data.truncated);
      setFromCache(data.from_cache);
      setActiveSessionId(data.session_id);
      refreshSessions();
    } catch (err) {
      if (err.status === 402) {
        setCapHit(true);
      } else {
        setError(err.message || "Couldn't generate vendor Q&A — try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleSelectSession(sessionId) {
    setError("");
    try {
      const session = await api.getSession(sessionId);
      setActiveSessionId(sessionId);
      const last = session.messages[session.messages.length - 1];
      setJdText(last ? last.question : "");
      setItems(last ? last.response.items : null);
      setTruncated(last ? last.response.truncated : false);
      setFromCache(true);
    } catch (err) {
      setError(err.message || "Couldn't load that chat.");
    }
  }

  async function handleDeleteSession(sessionId) {
    try {
      await api.deleteSession(sessionId);
      if (sessionId === activeSessionId) {
        setActiveSessionId(null);
        setItems(null);
        setJdText("");
      }
      refreshSessions();
    } catch (err) {
      setError(err.message || "Couldn't delete that chat — try again.");
    }
  }

  async function handleRenameSession(sessionId, title) {
    try {
      await api.renameSession(sessionId, title);
      refreshSessions();
    } catch (err) {
      setError(err.message || "Couldn't rename that chat — try again.");
    }
  }

  async function handleSearch(query) {
    try {
      const results = query.trim()
        ? await api.searchSessions("resume_sync_qa", query.trim())
        : await api.listSessions("resume_sync_qa");
      setSessions(results);
    } catch {
      // ignore
    }
  }

  return (
    <div className="flex -mx-6">
      <ChatHistoryPanel
        sessions={sessions}
        activeSessionId={activeSessionId}
        onNewChat={() => { setActiveSessionId(null); setItems(null); setJdText(""); }}
        onSelect={handleSelectSession}
        onDelete={handleDeleteSession}
        onRename={handleRenameSession}
        onSearch={handleSearch}
      />
      <div className="flex-1 px-6">
        <div className="border border-gray-200 rounded-xl p-4 mb-4">
          <p className="text-sm font-medium text-gray-900 mb-2">Paste the job description the vendor sent</p>
          <textarea
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            placeholder="Paste the job description here..."
            rows={7}
            className="w-full border border-gray-300 rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
          />
          <button
            type="button"
            onClick={handleGenerate}
            disabled={busy}
            className="w-full mt-3 bg-accent text-white rounded-lg py-2.5 text-sm font-medium hover:brightness-110 transition disabled:opacity-60"
          >
            {busy ? "📞 Simulating the vendor screening call..." : "📞 Prep for this vendor call"}
          </button>
        </div>

        {capHit && <UpgradeBanner message="You've hit today's free resume-sync limit." />}
        {error && <p className="text-sm text-red-600 mb-4">{error}</p>}
        {truncated && <TruncationBanner />}

        {items && (
          <>
            {fromCache && (
              <p className="text-xs text-emerald-700 mb-3">
                ⚡ Loaded from a previous sync for this exact JD — no tokens spent regenerating it.
              </p>
            )}
            <div className="space-y-3">
              {items.map((item, idx) => {
                const meta = CATEGORY_STYLE[item.category] || { emoji: "📌", color: "#607D8B" };
                return (
                  <div key={idx} className="rounded-xl p-4 bg-white border-l-4" style={{ borderColor: meta.color, boxShadow: "0 1px 3px rgba(0,0,0,0.08)" }}>
                    <span className="text-white text-[11px] font-bold px-2.5 py-0.5 rounded-full" style={{ background: meta.color }}>
                      {meta.emoji} {item.category.toUpperCase()}
                    </span>
                    <p className="text-sm font-semibold text-gray-900 mt-2 mb-1.5">🗣️ Vendor: {item.question}</p>
                    <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">🙋 You: {item.answer}</p>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
