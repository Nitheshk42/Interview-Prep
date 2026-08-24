import { useState, useRef, useEffect } from "react";
import { useAuth } from "../context/AuthContext";
import { useProvider, PROVIDERS } from "../context/ProviderContext";
import * as api from "../api/client";
import { SECTIONS, PHASE_LABELS } from "../sections";
import PlanPicker from "./PlanPicker";

const TIER_LABELS = { sprint: "Career Sprint", student: "Student", pro_monthly: "Pro" };

// Redesigned per the reviewed prototype: avatar + compact provider select up top, grouped nav
// with section labels (Before interview / During interview / Coming soon), and the
// upload/feedback/logout controls - which used to sit as a wall of always-visible inputs at the
// bottom - collapsed into a small icon row. Feedback opens a small popover instead of a
// permanently-open textarea; upload triggers a hidden file input via the icon button.
//
// Responsive: on screens narrower than the `lg` breakpoint, this renders as a slide-out drawer
// (App.jsx owns the open/closed state and a hamburger button in a mobile top bar) instead of a
// permanently-visible column, which would otherwise crush the main content on a phone. At `lg`
// and above it behaves exactly as before - a normal static column, the mobile-only prop values
// have no effect.
export default function Sidebar({ section, onSectionChange, mobileOpen, onMobileClose }) {
  const { username, profile, logout } = useAuth();
  const { provider, setProvider } = useProvider();
  const [menuOpen, setMenuOpen] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [feedbackMsg, setFeedbackMsg] = useState("");
  const [reprocessing, setReprocessing] = useState(false);
  const [paymentStatus, setPaymentStatus] = useState(null); // null = not loaded yet, {active:false} = inactive
  const [pickerOpen, setPickerOpen] = useState(false);
  const fileInputRef = useRef(null);
  const menuRef = useRef(null);

  // Fails silently (payments aren't guaranteed to be turned on - see routers/payments.py) -
  // this badge simply doesn't render if the status check errors, rather than showing anything
  // scary to a user on a build where monetization isn't configured yet.
  useEffect(() => {
    api.getPaymentStatus().then(setPaymentStatus).catch(() => setPaymentStatus({ active: false }));
  }, []);

  function daysLeft(expiresAt) {
    if (!expiresAt) return null;
    const ms = new Date(expiresAt).getTime() - Date.now();
    return Math.max(0, Math.ceil(ms / (1000 * 60 * 60 * 24)));
  }

  // Close the profile dropdown on an outside click.
  useEffect(() => {
    function onClickOutside(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuOpen(false);
        setFeedbackOpen(false);
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

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
          Authorization: `Bearer ${sessionStorage.getItem("studysager_token")}`,
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

  function selectSection(key) {
    onSectionChange(key);
    onMobileClose?.();
  }

  return (
    <>
      {/* Backdrop - mobile only, only rendered while the drawer is open. Tapping it closes the
          drawer, same as tapping outside a modal. */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/30 z-30 lg:hidden"
          onClick={onMobileClose}
        />
      )}
      <aside
        className={`w-60 shrink-0 border-r border-gray-200 bg-white p-3 flex flex-col gap-5 min-h-screen
          fixed inset-y-0 left-0 z-40 transform transition-transform duration-200 overflow-y-auto
          ${mobileOpen ? "translate-x-0" : "-translate-x-full"}
          lg:static lg:translate-x-0 lg:z-auto`}
      >
      <div className="relative" ref={menuRef}>
        <button
          type="button"
          onClick={() => setMenuOpen((v) => !v)}
          className="w-full flex items-center gap-2.5 px-1 py-1 rounded-lg hover:bg-gray-50 transition"
        >
          <div className="w-8 h-8 rounded-full bg-accent/10 text-accent flex items-center justify-center text-xs font-medium shrink-0">
            {initials}
          </div>
          <div className="min-w-0 flex-1 text-left">
            <p className="text-sm font-medium text-gray-900 truncate">{username}</p>
            <p className="text-[11px] text-gray-400">{profile?.level ? `${profile.level} level` : "Level not set"}</p>
          </div>
          <span className="text-gray-400 text-xs shrink-0">{menuOpen ? "▲" : "▼"}</span>
        </button>

        {menuOpen && (
          <div className="absolute left-0 right-0 top-full mt-1 bg-white border border-gray-200 rounded-xl shadow-lg py-1 z-20">
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.doc"
              onChange={handleReupload}
              disabled={reprocessing}
              className="hidden"
            />
            <MenuItem icon="📄" label={reprocessing ? "Uploading..." : "Upload a different resume"} onClick={() => fileInputRef.current?.click()} disabled={reprocessing} />
            <MenuItem icon="💬" label="Send feedback" onClick={() => setFeedbackOpen((v) => !v)} />
            {feedbackOpen && (
              <div className="px-3 py-2 border-t border-gray-100">
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
            <div className="border-t border-gray-100 my-1" />
            <MenuItem icon="🚪" label="Log out" onClick={logout} />
          </div>
        )}
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

      {paymentStatus?.active && (
        <div className="px-2.5 py-2 rounded-lg bg-accent/10 text-accent text-[11px] font-medium">
          🚀 {TIER_LABELS[paymentStatus.tier] || paymentStatus.tier} active
          {paymentStatus.expires_at
            ? ` — ${daysLeft(paymentStatus.expires_at)} day${daysLeft(paymentStatus.expires_at) === 1 ? "" : "s"} left`
            : " — renews monthly"}
        </div>
      )}
      {paymentStatus && !paymentStatus.active && (
        <button
          type="button"
          onClick={() => setPickerOpen(true)}
          className="w-full text-[11px] font-medium text-left px-2.5 py-2 rounded-lg border border-accent/30 text-accent hover:bg-accent/5 transition"
        >
          🚀 Upgrade
        </button>
      )}
      {pickerOpen && <PlanPicker onClose={() => setPickerOpen(false)} />}

      <nav className="flex flex-col gap-3">
        {["before", "during"].map((phase) => (
          <div key={phase}>
            <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide px-2 mb-1">
              {PHASE_LABELS[phase]}
            </p>
            <div className="space-y-0.5">
              {SECTIONS.filter((s) => s.phase === phase).map((s) => (
                <SectionButton key={s.key} s={s} section={section} onSectionChange={selectSection} />
              ))}
            </div>
          </div>
        ))}
        {SECTIONS.filter((s) => !s.phase).length > 0 && (
          <div>
            <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide px-2 mb-1">Coming soon</p>
            <div className="space-y-0.5">
              {SECTIONS.filter((s) => !s.phase).map((s) => (
                <SectionButton key={s.key} s={s} section={section} onSectionChange={selectSection} />
              ))}
            </div>
          </div>
        )}
      </nav>
      </aside>
    </>
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

function MenuItem({ icon, label, onClick, disabled }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="w-full flex items-center gap-2.5 text-left text-[13px] text-gray-700 px-3 py-2 hover:bg-gray-50 transition disabled:opacity-50"
    >
      <span className="text-base shrink-0">{icon}</span>
      <span className="truncate">{label}</span>
    </button>
  );
}
