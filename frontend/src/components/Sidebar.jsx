import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useProvider, PROVIDERS } from "../context/ProviderContext";
import * as api from "../api/client";
import { SECTIONS, PHASE_LABELS } from "../sections";

export default function Sidebar({ section, onSectionChange }) {
  const { username, profile, logout } = useAuth();
  const { provider, setProvider } = useProvider();
  const [feedback, setFeedback] = useState("");
  const [feedbackMsg, setFeedbackMsg] = useState("");
  const [reprocessing, setReprocessing] = useState(false);

  async function submitFeedback() {
    if (!feedback.trim()) {
      setFeedbackMsg("Write something before submitting.");
      return;
    }
    try {
      await fetch(`${import.meta.env.VITE_API_URL || "http://localhost:8000"}/auth/feedback`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("studysager_token")}`,
        },
        body: JSON.stringify({ message: feedback }),
      });
      setFeedback("");
      setFeedbackMsg("✅ Thanks — feedback saved!");
    } catch {
      setFeedbackMsg("Something went wrong.");
    }
  }

  async function handleReupload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!confirm("Uploading a new resume will wipe your current resume's data. Continue?")) return;
    setReprocessing(true);
    try {
      await api.reprocessResume(file);
      alert("✅ New resume is now active!");
    } catch (err) {
      alert(err.message || "Something went wrong.");
    } finally {
      setReprocessing(false);
    }
  }

  return (
    <aside className="w-64 shrink-0 border-r border-gray-200 bg-white p-4 flex flex-col gap-4 min-h-screen">
      <div>
        <p className="font-medium text-gray-900">👤 {username}</p>
        <p className="text-xs text-gray-500">Level: {profile?.level || "Not set"}</p>
      </div>

      <div>
        <p className="text-xs font-medium text-gray-500 mb-1">🧠 Answer engine</p>
        <select
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
          className="w-full text-sm border border-gray-300 rounded-lg px-2 py-1.5"
        >
          {Object.entries(PROVIDERS).map(([key, label]) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </select>
        <p className="text-[10px] text-gray-400 mt-1">
          Switches which LLM generates answers across every tab. Groq's 70B model is the most
          capable but can be slower under load — Gemini often responds faster.
        </p>
      </div>

      <div>
        <p className="text-xs font-medium text-gray-500 mb-2">🧭 Jump to</p>
        <div className="space-y-3">
          {["before", "during"].map((phase) => (
            <div key={phase}>
              <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide px-2 mb-1">
                {PHASE_LABELS[phase]}
              </p>
              <div className="space-y-1">
                {SECTIONS.filter((s) => s.phase === phase).map((s) => (
                  <SectionButton key={s.key} s={s} section={section} onSectionChange={onSectionChange} />
                ))}
              </div>
            </div>
          ))}
          {SECTIONS.filter((s) => !s.phase).length > 0 && (
            <div>
              <div className="border-t border-gray-100 pt-2 space-y-1">
                {SECTIONS.filter((s) => !s.phase).map((s) => (
                  <SectionButton key={s.key} s={s} section={section} onSectionChange={onSectionChange} />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="border-t border-gray-200 pt-3">
        <p className="text-xs font-medium text-gray-500 mb-1">📄 Upload a different resume</p>
        <input
          type="file"
          accept=".pdf,.docx,.doc"
          onChange={handleReupload}
          disabled={reprocessing}
          className="text-xs w-full"
        />
      </div>

      <button
        type="button"
        onClick={logout}
        className="text-sm border border-gray-300 rounded-lg py-1.5 hover:bg-gray-50 transition"
      >
        🚪 Logout
      </button>

      <div className="border-t border-gray-200 pt-3 mt-auto">
        <p className="text-xs font-medium text-gray-500 mb-1">💬 Send feedback</p>
        <textarea
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          placeholder="What's working, what's not, what would help?"
          className="w-full text-xs border border-gray-300 rounded-lg p-2 mb-1"
          rows={3}
        />
        <button
          type="button"
          onClick={submitFeedback}
          className="w-full text-xs border border-gray-300 rounded-lg py-1.5 hover:bg-gray-50 transition"
        >
          Submit feedback
        </button>
        {feedbackMsg && <p className="text-xs text-gray-500 mt-1">{feedbackMsg}</p>}
      </div>
    </aside>
  );
}

function SectionButton({ s, section, onSectionChange }) {
  return (
    <button
      type="button"
      disabled={!s.enabled}
      onClick={() => onSectionChange(s.key)}
      className={`w-full text-left text-sm px-2 py-1.5 rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed ${
        section === s.key ? "bg-accent/10 text-accent font-medium" : "text-gray-700 hover:bg-gray-50"
      }`}
    >
      {s.label}
      {!s.enabled && <span className="text-[10px] text-gray-400 ml-1">(soon)</span>}
    </button>
  );
}
