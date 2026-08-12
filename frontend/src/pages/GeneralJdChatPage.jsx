import { useState } from "react";
import * as api from "../api/client";
import { useProvider } from "../context/ProviderContext";
import TruncationBanner from "../components/TruncationBanner";

const LEVEL_ORDER = ["Junior", "Mid-Level", "Senior", "Architect"];
const LEVEL_META = {
  "Junior": { emoji: "🌱", color: "#4CAF50" },
  "Mid-Level": { emoji: "⚙️", color: "#2196F3" },
  "Senior": { emoji: "🎯", color: "#FF9800" },
  "Architect": { emoji: "🏛️", color: "#9C27B0" },
};

// Mirrors src/general_jd_chat.py: paste a JD, get interview Q&A generated purely from general
// LLM knowledge - no resume, no personal context at all - at all four seniority levels. The
// "no resume grounding" counterpart to My JD Answers.
export default function GeneralJdChatPage() {
  const { provider } = useProvider();
  const [jdText, setJdText] = useState("");
  const [items, setItems] = useState(null);
  const [truncated, setTruncated] = useState(false);
  const [busy, setBusy] = useState(false);
  const [moreBusy, setMoreBusy] = useState(false);
  const [error, setError] = useState("");

  async function handleGenerate() {
    if (!jdText.trim()) {
      setError("Please paste a job description first.");
      return;
    }
    setError("");
    setBusy(true);
    try {
      const data = await api.generateGeneralJdQuestions({ jdText, provider, numQuestions: 6 });
      setItems(data.items);
      setTruncated(data.truncated);
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
      const data = await api.generateGeneralJdQuestions({
        jdText, provider, numQuestions: 5,
        excludeQuestions: items.map((i) => i.question),
      });
      setItems((prev) => [...prev, ...data.items]);
      setTruncated(data.truncated);
    } catch (err) {
      setError(err.message || "Couldn't generate more questions — try again.");
    } finally {
      setMoreBusy(false);
    }
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="rounded-2xl p-6 mb-6 text-white" style={{ background: "linear-gradient(135deg, #6c5ce7 0%, #1a73e8 100%)" }}>
        <p className="text-xl font-bold">🧠 General JD Answers</p>
        <p className="text-sm opacity-90 mt-1">
          Paste a job description — get interview Q&amp;A generated purely from general domain
          knowledge, the way a general-purpose AI would answer with just the JD and nothing
          else. No resume, no personal context — pure LLM knowledge, at all four seniority
          levels.
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
          {busy ? "🧠 Generating questions and level-by-level answers..." : "🧠 Generate General Q&A"}
        </button>
      </div>

      {error && <p className="text-sm text-red-600 mb-4">{error}</p>}

      {items && (
        <>
          {truncated && <TruncationBanner />}
          <p className="text-sm text-emerald-700 mb-4">✅ {items.length} question(s) generated — no resume context used.</p>

          <div className="space-y-6">
            {items.map((item, idx) => (
              <QuestionBlock key={idx} index={idx + 1} item={item} />
            ))}
          </div>

          <button
            type="button"
            onClick={handleMore}
            disabled={moreBusy}
            className="w-full mt-6 border border-gray-300 rounded-lg py-2.5 text-sm font-medium hover:bg-gray-50 transition disabled:opacity-60"
          >
            {moreBusy ? "🧠 Generating 5 more (no repeats)..." : "➕ 5 more questions"}
          </button>
        </>
      )}
    </div>
  );
}

function QuestionBlock({ index, item }) {
  return (
    <div>
      <p className="text-sm font-semibold text-gray-900 mb-2">Q{index}. {item.question}</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {LEVEL_ORDER.map((level) => {
          const meta = LEVEL_META[level];
          const answer = (item.answers[level] || "").trim();
          return (
            <div key={level}>
              <div className="border-l-4 pl-2 mb-1" style={{ borderColor: meta.color }}>
                <span className="text-sm font-bold" style={{ color: meta.color }}>{meta.emoji} {level}</span>
              </div>
              <div className="border border-gray-200 rounded-lg p-3 bg-gray-50 text-sm text-gray-700 whitespace-pre-wrap">
                {answer || <span className="italic text-gray-400">No answer generated for this level.</span>}
              </div>
            </div>
          );
        })}
      </div>
      <hr className="mt-4 border-gray-100" />
    </div>
  );
}
