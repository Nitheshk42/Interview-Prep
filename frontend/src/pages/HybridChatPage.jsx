import { useState, useEffect, useCallback, useRef } from "react";
import * as api from "../api/client";
import { useProvider } from "../context/ProviderContext";
import MicButton from "../components/MicButton";
import ChatHistoryPanel from "../components/ChatHistoryPanel";
import TruncationBanner from "../components/TruncationBanner";
import UpgradeBanner from "../components/UpgradeBanner";

const SECTION = "hybrid";

const ROUTE_COLORS = {
  RESUME_FACT: { text: "text-emerald-600", border: "border-emerald-500", bg: "bg-emerald-50" },
  TECHNICAL_DEEP_DIVE: { text: "text-amber-600", border: "border-amber-500", bg: "bg-amber-50" },
  BOTH: { text: "text-blue-600", border: "border-blue-500", bg: "bg-blue-50" },
};

// Mirrors src/hybrid_chat.py: route the question, then answer it two independent ways side by
// side - strictly resume-grounded, and an interview-style technical deep-dive - so you always
// have both versions ready regardless of which way an interviewer phrases the question. This is
// the "During Interview" tab - built for fast lookup mid-interview, with a saved-chats rail so a
// question you already asked (and its two answers) can be reopened instantly, at no token cost.
export default function HybridChatPage() {
  const { provider } = useProvider();
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [history, setHistory] = useState([]); // [{question, category, reason, resume, technical}]
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [capHit, setCapHit] = useState(false);
  const bottomRef = useRef(null);

  // Jump straight to the newest question whenever the thread changes, instead of leaving the
  // user to scroll down and hunt for what they just asked.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [history]);

  const refreshSessions = useCallback(() => {
    api.listSessions(SECTION).then(setSessions).catch(() => {});
  }, []);

  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  function handleNewChat() {
    setActiveSessionId(null);
    setHistory([]);
    setError("");
  }

  async function handleSelectSession(sessionId) {
    setError("");
    try {
      const session = await api.getSession(sessionId);
      setActiveSessionId(sessionId);
      setHistory(session.messages.map((t) => ({ question: t.question, ...t.response })));
    } catch (err) {
      setError(err.message || "Couldn't load that chat.");
    }
  }

  async function handleDeleteSession(sessionId) {
    try {
      await api.deleteSession(sessionId);
      if (sessionId === activeSessionId) handleNewChat();
      refreshSessions();
    } catch {
      // ignore
    }
  }

  async function handleRenameSession(sessionId, title) {
    try {
      await api.renameSession(sessionId, title);
      refreshSessions();
    } catch {
      // ignore
    }
  }

  async function handleSearch(query) {
    try {
      const results = query.trim() ? await api.searchSessions(SECTION, query.trim()) : await api.listSessions(SECTION);
      setSessions(results);
    } catch {
      // ignore
    }
  }

  async function sendQuestion(raw) {
    const question = (raw || "").trim();
    if (!question || busy) return;
    setInput("");
    setError("");
    setCapHit(false);
    setBusy(true);
    try {
      const data = await api.askHybridChat(question, provider);
      setHistory((h) => [...h, { question, ...data }]);

      let sessionId = activeSessionId;
      if (!sessionId) {
        const created = await api.createSession(SECTION, question);
        sessionId = created.id;
        setActiveSessionId(sessionId);
      }
      await api.appendSessionMessage(sessionId, question, data);
      refreshSessions();
    } catch (err) {
      if (err.status === 402) {
        setCapHit(true);
      } else {
        setError(err.message || "Something went wrong.");
      }
    } finally {
      setBusy(false);
    }
  }

  function handleSend(e) {
    e.preventDefault();
    sendQuestion(input);
  }

  return (
    <div className="flex">
      <ChatHistoryPanel
        sessions={sessions}
        activeSessionId={activeSessionId}
        onNewChat={handleNewChat}
        onSelect={handleSelectSession}
        onDelete={handleDeleteSession}
        onRename={handleRenameSession}
        onSearch={handleSearch}
      />
      {/* The 100vh-based height ignores anything above it in normal flow - on mobile that's the
          sticky top bar in App.jsx (~56px), so it's subtracted here specifically for < lg; at
          lg+ there's no top bar, so the calc reverts to the original. */}
      <div className="p-6 max-w-6xl mx-auto flex-1 h-[calc(100vh-2rem-56px)] lg:h-[calc(100vh-2rem)] flex flex-col min-h-0">
        <h1 className="text-xl font-medium text-gray-900 mb-1 shrink-0">🔀 Hybrid Chat</h1>
        <p className="text-sm text-gray-500 mb-4 shrink-0">
          Real routing decision + two independently generated answers, so you always have an
          interview-ready technical answer alongside the resume-grounded one.
        </p>

        {/* Only this turn list scrolls - the input bar below stays pinned at the bottom of the
            panel instead of drifting wherever the page happens to end. */}
        <div className="flex-1 min-h-0 overflow-y-auto space-y-6 pr-1">
          {history.map((turn, i) => (
            <TurnCard key={i} turn={turn} />
          ))}
          {busy && <p className="text-sm text-gray-400">🧭 Routing question and generating both answers...</p>}
          <div ref={bottomRef} />
        </div>

        {capHit && <UpgradeBanner message="You've hit today's free question limit." />}
        {error && <p className="text-sm text-red-600 mt-2 shrink-0">{error}</p>}

        <form onSubmit={handleSend} className="mt-3 flex gap-2 shrink-0">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your experience or technical concepts..."
            autoComplete="off"
            disabled={busy}
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:bg-gray-50"
          />
          <MicButton
            value={input}
            disabled={busy}
            onResult={(text) => setInput((prev) => (prev ? `${prev} ${text}` : text))}
            onAutoSubmit={(text) => sendQuestion(text)}
          />
          <button
            type="submit"
            disabled={busy}
            className="bg-accent text-white rounded-lg px-4 py-2 text-sm font-medium hover:brightness-110 transition disabled:opacity-60"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}

function TurnCard({ turn }) {
  const colors = ROUTE_COLORS[turn.category] || { text: "text-gray-600", border: "border-gray-400", bg: "bg-gray-50" };

  return (
    <div className="border border-gray-200 rounded-xl p-4 bg-white">
      <p className="text-sm font-medium text-gray-900 mb-2">🙋 {turn.question}</p>

      <div className={`border ${colors.border} ${colors.bg} rounded-lg px-3 py-2 mb-4 text-xs`}>
        🧭 <span className={`font-semibold ${colors.text}`}>Routing decision: {turn.category}</span>
        <div className="text-gray-600 mt-0.5">{turn.reason}</div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <SideAnswer emoji="📄" title="From Your Resume" subtitle="Strictly grounded in retrieved chunks" color="emerald" side={turn.resume} />
        <SideAnswer emoji="🧠" title="Technical Deep-Dive" subtitle="Interview follow-up style: approach, challenges, resolution" color="amber" side={turn.technical} />
      </div>
    </div>
  );
}

function SideAnswer({ emoji, title, subtitle, color, side }) {
  const [showChunks, setShowChunks] = useState(false);
  const border = color === "emerald" ? "border-emerald-500" : "border-amber-500";
  const text = color === "emerald" ? "text-emerald-700" : "text-amber-700";

  return (
    <div>
      <div className={`border-l-4 ${border} pl-3 mb-2`}>
        <p className={`text-sm font-bold ${text}`}>{emoji} {title}</p>
        <p className="text-[11px] text-gray-500">{subtitle}</p>
      </div>
      {side.truncated && <TruncationBanner variant="single" compact />}
      <div className="border border-gray-200 rounded-lg p-3 bg-gray-50 text-sm text-gray-800 whitespace-pre-wrap">
        {side.answer}
      </div>
      <button
        type="button"
        onClick={() => setShowChunks((v) => !v)}
        className="text-[11px] text-accent font-medium hover:underline mt-1"
      >
        {showChunks ? "Hide retrieved chunks ▲" : `Show retrieved chunks (${side.retrieved.length}) ▼`}
      </button>
      {showChunks && (
        <div className="space-y-1.5 mt-2">
          {side.full_resume_used && (
            <p className="text-[10px] text-gray-500">
              This question asked for a full list/timeline, so every chunk of the resume was
              used instead of a similarity-ranked subset.
            </p>
          )}
          {side.retrieved.map((c, i) => (
            <details key={i} className="border border-gray-200 rounded-lg p-2 bg-white">
              <summary className="cursor-pointer text-[11px] text-gray-600 flex items-center justify-between gap-2">
                <span>Chunk {i + 1}</span>
                {side.full_resume_used ? (
                  <span className="text-gray-400">included in full fetch</span>
                ) : (
                  <span className="text-gray-500">{c.match_pct}% match</span>
                )}
              </summary>
              <pre className="text-[11px] whitespace-pre-wrap text-gray-700 mt-1">{c.content}</pre>
            </details>
          ))}
        </div>
      )}
    </div>
  );
}
