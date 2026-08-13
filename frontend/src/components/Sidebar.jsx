import { useState, useRef } from "react";
import { useAuth } from "../context/AuthContext";
import { useProvider, PROVIDERS } from "../context/ProviderContext";
import * as api from "../api/client";
import { SECTIONS, PHASE_LABELS } from "../sections";

// Redesigned per the reviewed prototype: avatar + compact provider select up top, grouped nav
// with section labels (Before interview / During interview / Coming soon), and the
// upload/feedback/logout controls - which used to sit as a wall of always-visible inputs at the
// bottom - collapsed into a small icon row. Feedback opens a small popover instead of a
// permanently-open textarea; upload triggers a hidden file input via the icon button.
export default function Sidebar({ section, onSectionChange }) {
  const { username, profile, logout } = useAuth();
  const { provider, setProvider } = useProvider();
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [feedbackMsg, setFeedbackMsg] = useState("");
  const [reprocessing, setReprocessing] = useState(false);
  const fileInputRef = useRef(null);

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
      setFeedbackMsg("Thanks — feedback saved.");
      setTimeout(() => { setFeedbackOpen(false); setFeedbackMsg(""); }, 1200);
    } catch {
      setFeedbackMsg("Something went wrong.");
    }
  }

  async function handleReupload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!confirm("Uploading a new resume will wipe your current resume's data. Continue?")) {
      e.target.value = "";
      return;
    }
    setReprocessing(true);
    try {
      await api.reprocessResume(file);
      alert("New resume is now active.");
    } catch (err) {
      alert(err.message || "Something went wrong.");
    } finally {
      setReprocessing(false);
      e.target.value = "";
    }
  }

  const initials = (username || "?").slice(0, 2).toUpperCase();

  return (
    <aside className="w-60 shrink-0 border-r border-gray-200 bg-white p-3 flex flex-col gap-5 min-h-screen">
      <div className="flex items-center gap-2.5 px-1">
        <div className="w-8 h-8 rounded-full bg-accent/10 text-accent flex items-center justify-center text-xs font-medium shrink-0">
          {initials}
        </div>
        <div className="min-w-0">
          <p className="text-sm font-medium text-gray-900 truncate">{username}</p>
          <p className="text-[11px] text-gray-400">{profile?.level ? `${profile.level} level` : "Level not set"}</p>
        </div>
      </div>

      <div className="px-1">
        <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-1">Answer engine</p>
        <select
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
          className="w-full text-xs border border-gray-300 rounded-lg px-2 py-1.5"
        >
          {Object.entries(PROVIDERS).map(([key, label]) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </select>
      </div>

      <nav className="flex flex-col gap-3">
        {["before", "during"].map((phase) => (
          <div key={phase}>
            <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide px-2 mb-1">
              {PHASE_LABELS[phase]}
            </p>
            <div className="space-y-0.5">
              {SECTIONS.filter((s) => s.phase === phase).map((s) => (
                <SectionButton key={s.key} s={s} section={section} onSectionChange={onSectionChange} />
              ))}
            </div>
          </div>
        ))}
        {SECTIONS.filter((s) => !s.phase).length > 0 && (
          <div>
            <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide px-2 mb-1">Coming soon</p>
            <div className="space-y-0.5">
              {SECTIONS.filter((s) => !s.phase).map((s) => (
                <SectionButton key={s.key} s={s} section={section} onSectionChange={onSectionChange} />
              ))}
            </div>
          </div>
        )}
      </nav>

      <div className="mt-auto pt-3 border-t border-gray-100 relative">
        <div className="flex items-center justify-around">
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.doc"
            onChange={handleReupload}
            disabled={reprocessing}
            className="hidden"
          />
          <IconButton
            label="Upload a different resume"
            icon="📄"
            onClick={() => fileInputRef.current?.click()}
            busy={reprocessing}
          />
          <IconButton
            label="Send feedback"
            icon="💬"
            onClick={() => setFeedbackOpen((v) => !v)}
            active={feedbackOpen}
          />
          <IconButton label="Log out" icon="🚪" onClick={logout} />
        </div>

        {feedbackOpen && (
          <div className="absolute bottom-12 left-0 right-0 bg-white border border-gray-200 rounded-xl shadow-lg p-3 z-10">
            <p className="text-xs font-medium text-gray-700 mb-1.5">Send feedback</p>
            <textarea
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="What's working, what's not, what would help?"
              className="w-full text-xs border border-gray-300 rounded-lg p-2 mb-1.5"
              rows={3}
              autoFocus
            />
            <button
              type="button"
              onClick={submitFeedback}
              className="w-full text-xs border border-gray-300 rounded-lg py-1.5 hover:bg-gray-50 transition"
            >
              Submit
            </button>
            {feedbackMsg && <p className="text-[11px] text-gray-500 mt-1">{feedbackMsg}</p>}
          </div>
        )}
      </div>
    </aside>
  );
}

function SectionButton({ s, section, onSectionChange }) {
  const active = section === s.key;
  return (
    <button
      type="button"
      disabled={!s.enabled}
      onClick={() => onSectionChange(s.key)}
      className={`w-full text-left text-[13px] px-2 py-1.5 rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2 ${
        active ? "bg-accent/10 text-accent" : "text-gray-700 hover:bg-gray-50"
      }`}
    >
      <span className="flex-1 truncate">{s.label}</span>
      {!s.enabled && <span className="text-[10px] text-gray-400 shrink-0">soon</span>}
    </button>
  );
}

function IconButton({ label, icon, onClick, active, busy }) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={onClick}
      disabled={busy}
      className={`p-1.5 rounded-lg transition text-base disabled:opacity-50 ${
        active ? "bg-accent/10" : "hover:bg-gray-100"
      }`}
    >
      {busy ? "⏳" : icon}
    </button>
  );
}
