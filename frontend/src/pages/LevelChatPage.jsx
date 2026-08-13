import { useState, useEffect, useCallback } from "react";
import * as api from "../api/client";
import { useProvider } from "../context/ProviderContext";
import MicButton from "../components/MicButton";
import ChatHistoryPanel from "../components/ChatHistoryPanel";
import TruncationBanner from "../components/TruncationBanner";

const SECTION = "level";

const LEVEL_ORDER = ["Junior", "Mid-Level", "Senior", "Architect"];

const LEVEL_META = {
  "Junior": { emoji: "🌱", border: "border-emerald-500", text: "text-emerald-700", desc: "Simple, foundational" },
  "Mid-Level": { emoji: "⚙️", border: "border-blue-500", text: "text-blue-700", desc: "Concrete detail & decisions" },
  "Senior": { emoji: "🎯", border: "border-amber-500", text: "text-amber-700", desc: "Tradeoffs & depth" },
  "Architect": { emoji: "🏛️", border: "border-purple-500", text: "text-purple-700", desc: "System-level design" },
};

// Mirrors src/level_chat.py: one question, answered at all four seniority levels side by side,
// so you can see how the same story should be told differently depending on who's interviewing
// you. Every answer is written in first person, grounded in the actual resume, per the backend
// prompt rules - not a generic AI summary.
export default function LevelChatPage() {
  const { provider } = useProvider();
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [history, setHistory] = useState([]); // [{question, answers: {level: HybridSide}}]
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

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
      setHistory(session.messages.map((t) => ({ question: t.question, answers: t.response.answers })));
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
    setBusy(true);
    try {
      const data = await api.askLevelChat(question, provider);
      setHistory((h) => [...h, { question, answers: data.answers }]);

      let sessionId = activeSessionId;
      if (!sessionId) {
        const created = await api.createSession(SECTION, question);
        sessionId = created.id;
        setActiveSessionId(sessionId);
      }
      await api.appendSessionMessage(sessionId, question, data);
      refreshSessions();
    } catch (err) {
      setError(err.message || "Something went wrong.");
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
      <div className="p-6 max-w-6xl mx-auto flex-1">
        <h1 className="text-xl font-medium text-gray-900 mb-1">🪜 My EXP Level Answers</h1>
        <p className="text-sm text-gray-500 mb-4">
          See how the same question should be answered depending on the seniority you're interviewing for.
        </p>

        <div className="space-y-8">
          {history.map((turn, i) => (
            <TurnCard key={i} turn={turn} />
          ))}
          {busy && <p className="text-sm text-gray-400">🪜 Preparing all four levels...</p>}
        </div>

        {error && <p className="text-sm text-red-600 mt-4">{error}</p>}

        <form onSubmit={handleSend} className="mt-6 flex gap-2 sticky bottom-4 bg-white">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question to see it answered at every level..."
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
  return (
    <div className="border border-gray-200 rounded-xl p-4 bg-white">
      <p className="text-sm font-medium text-gray-900 mb-3">🙋 {turn.question}</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {LEVEL_ORDER.map((level) => (
          <LevelCard key={level} level={level} side={turn.answers[level]} />
        ))}
      </div>
    </div>
  );
}

function LevelCard({ level, side }) {
  const [showChunks, setShowChunks] = useState(false);
  const meta = LEVEL_META[level];

  return (
    <div>
      <div className={`border-l-4 ${meta.border} pl-3 mb-2`}>
        <p className={`text-sm font-bold ${meta.text}`}>{meta.emoji} {level}</p>
        <p className="text-[11px] text-gray-500">{meta.desc}</p>
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
