import { useState, useCallback, useEffect } from "react";
import * as api from "../api/client";
import { useProvider } from "../context/ProviderContext";
import TruncationBanner from "../components/TruncationBanner";
import ChatHistoryPanel from "../components/ChatHistoryPanel";

const SECTION = "jd";

const CATEGORY_STYLE = {
  Technical: { emoji: "🛠️", color: "#2196F3" },
  Behavioral: { emoji: "🗣️", color: "#4CAF50" },
  Resume: { emoji: "📄", color: "#9C27B0" },
  Gap: { emoji: "⚠️", color: "#FF5722" },
  General: { emoji: "📌", color: "#607D8B" },
};

// Mirrors src/jd_chat.py: paste a JD, check whether it actually fits the resume's domain, then
// generate resume-grounded likely interview questions grouped by category.
//
// Saved chats: each JD you analyze is saved (including any "5 more" you generate). Reopening one
// replays the stored questions/answers/alignment check straight from the database - no LLM call,
// so it costs nothing, unlike pasting the same JD in again.
export default function JdChatPage() {
  const { provider } = useProvider();
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [jdText, setJdText] = useState("");
  const [items, setItems] = useState(null);
  const [alignment, setAlignment] = useState(null);
  const [truncated, setTruncated] = useState(false);
  const [activeCategory, setActiveCategory] = useState(null);
  const [busy, setBusy] = useState(false);
  const [moreBusy, setMoreBusy] = useState(false);
  const [error, setError] = useState("");

  const refreshSessions = useCallback(() => {
    api.listSessions(SECTION).then(setSessions).catch(() => {});
  }, []);

  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  function handleNewChat() {
    setActiveSessionId(null);
    setJdText("");
    setItems(null);
    setAlignment(null);
    setTruncated(false);
    setActiveCategory(null);
    setError("");
  }

  async function handleSelectSession(sessionId) {
    setError("");
    try {
      const session = await api.getSession(sessionId);
      const last = session.messages[session.messages.length - 1];
      if (!last) return;
      setActiveSessionId(sessionId);
      setJdText(last.question);
      setItems(last.response.items);
      setAlignment(last.response.alignment);
      setTruncated(!!last.response.truncated);
      setActiveCategory(last.response.items[0]?.category ?? null);
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

  async function persist(newItems, newAlignment, newTruncated) {
    let sessionId = activeSessionId;
    if (!sessionId) {
      const title = jdText.trim().split("\n")[0].slice(0, 60) || "New JD";
      const created = await api.createSession(SECTION, title);
      sessionId = created.id;
      setActiveSessionId(sessionId);
    }
    await api.appendSessionMessage(sessionId, jdText, { items: newItems, alignment: newAlignment, truncated: newTruncated });
    refreshSessions();
  }

  async function handleGenerate() {
    if (!jdText.trim()) {
      setError("Please paste a job description first.");
      return;
    }
    setError("");
    setBusy(true);
    try {
      const data = await api.generateJdQuestions({ jdText, provider, numQuestions: 5 });
      setItems(data.items);
      setAlignment(data.alignment);
      setTruncated(data.truncated);
      setActiveCategory(data.items[0]?.category ?? null);
      await persist(data.items, data.alignment, data.truncated);
    } catch (err) {
      setError(err.message || "Couldn't generate questions — try again.");
    } finally {
      setBusy(false);
    }
  }

  async function handleMore() {
    setMoreBusy(true);
    setError("");
    try {
      const data = await api.generateJdQuestions({
        jdText, provider, numQuestions: 5,
        excludeQuestions: items.map((i) => i.question),
        checkAlignment: false,
      });
      const merged = [...items, ...data.items];
      setItems(merged);
      setTruncated(data.truncated);
      await persist(merged, alignment, data.truncated);
    } catch (err) {
      setError(err.message || "Couldn't generate more questions — try again.");
    } finally {
      setMoreBusy(false);
    }
  }

  const counts = {};
  (items || []).forEach((i) => { counts[i.category] = (counts[i.category] || 0) + 1; });
  const categories = Object.keys(counts);

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
      <div className="p-6 max-w-4xl mx-auto flex-1">
      <div className="rounded-2xl p-6 mb-6 text-white" style={{ background: "linear-gradient(135deg, #1a73e8 0%, #6c5ce7 100%)" }}>
        <p className="text-xl font-bold">📋 My JD Answers</p>
        <p className="text-sm opacity-90 mt-1">
          Paste a job description — get the questions you're likely to be asked, matched against
          your actual resume, with answers ready to go.
        </p>
      </div>

      <div className="border border-gray-200 rounded-xl p-4 mb-4">
        <p className="text-sm font-medium text-gray-900 mb-2">Paste the job description</p>
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
          {busy ? "🔍 Checking domain fit and generating questions..." : "🎯 Generate Interview Prep"}
        </button>
      </div>

      {error && <p className="text-sm text-red-600 mb-4">{error}</p>}

      {items && (
        <>
          {truncated && <TruncationBanner />}
          {alignment && alignment.aligned !== "YES" && (
            <div className="border border-amber-400 bg-amber-50 rounded-lg px-4 py-3 mb-4 text-sm text-amber-800">
              {alignment.aligned === "NO" ? "🚫" : "⚠️"} <strong>Domain fit: {alignment.aligned}</strong> — {alignment.note}{" "}
              Questions below are still generated, but lean on the Gap category and answer honestly about what's actually transferable.
            </div>
          )}

          <div className="flex flex-wrap gap-2 mb-4">
            <div className="border border-gray-200 rounded-lg px-3 py-1.5 text-xs">
              <span className="font-semibold">{items.length}</span> total
            </div>
            {categories.map((cat) => {
              const meta = CATEGORY_STYLE[cat] || CATEGORY_STYLE.General;
              return (
                <button
                  key={cat}
                  type="button"
                  onClick={() => setActiveCategory(cat)}
                  className={`rounded-lg px-3 py-1.5 text-xs border transition ${
                    activeCategory === cat ? "text-white" : "text-gray-700 border-gray-200"
                  }`}
                  style={activeCategory === cat ? { background: meta.color, borderColor: meta.color } : {}}
                >
                  {meta.emoji} {cat} ({counts[cat]})
                </button>
              );
            })}
          </div>

          <div className="space-y-3">
            {items
              .filter((i) => i.category === activeCategory)
              .map((item, idx) => (
                <QaCard key={idx} item={item} index={idx + 1} />
              ))}
          </div>

          <button
            type="button"
            onClick={handleMore}
            disabled={moreBusy}
            className="w-full mt-6 border border-gray-300 rounded-lg py-2.5 text-sm font-medium hover:bg-gray-50 transition disabled:opacity-60"
          >
            {moreBusy ? "🔍 Generating 5 more (no repeats)..." : "➕ 5 more questions"}
          </button>
        </>
      )}
      </div>
    </div>
  );
}

function QaCard({ item, index }) {
  const meta = CATEGORY_STYLE[item.category] || CATEGORY_STYLE.General;
  return (
    <div className="rounded-xl p-4 bg-white border-l-4" style={{ borderColor: meta.color, boxShadow: "0 1px 3px rgba(0,0,0,0.08)" }}>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-white text-[11px] font-bold px-2.5 py-0.5 rounded-full" style={{ background: meta.color }}>
          {meta.emoji} {item.category.toUpperCase()}
        </span>
        <span className="text-xs text-gray-400">Q{index}</span>
      </div>
      <p className="text-sm font-semibold text-gray-900 mb-1.5">{item.question}</p>
      <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">{item.answer}</p>
    </div>
  );
}
