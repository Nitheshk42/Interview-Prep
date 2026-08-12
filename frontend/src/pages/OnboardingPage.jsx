import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import * as api from "../api/client";
import { SECTIONS, DEFAULT_SECTION } from "../sections";

const LEVELS = ["Junior", "Mid-Level", "Senior", "Architect"];

// Mirrors src/onboarding.py: resume upload, level picker, and a card-based multi-select for
// which sections to start with.
export default function OnboardingPage({ onDone }) {
  const { setProfile } = useAuth();
  const [file, setFile] = useState(null);
  const [level, setLevel] = useState(LEVELS[0]);
  const [picked, setPicked] = useState([SECTIONS.find((s) => s.key === DEFAULT_SECTION).label]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function togglePick(label) {
    setPicked((prev) =>
      prev.includes(label) ? prev.filter((l) => l !== label) : [...prev, label]
    );
  }

  async function handleSubmit() {
    setError("");
    if (!file) {
      setError("Please upload a resume file.");
      return;
    }
    setBusy(true);
    try {
      const favorites = picked.length ? picked : [SECTIONS.find((s) => s.key === DEFAULT_SECTION).label];
      const data = await api.completeOnboarding(file, level, favorites);
      setProfile(data.profile);
      onDone?.();
    } catch (err) {
      setError(err.message || "Something went wrong processing your resume.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 py-10 px-4">
      <div className="max-w-3xl mx-auto">
        <h1 className="text-2xl font-medium text-gray-900">👋 Welcome to StudySage</h1>
        <p className="text-gray-500 mt-1 mb-8">
          Let's get you set up — upload your resume and pick the level you're interviewing for.
        </p>

        <section className="mb-8">
          <h2 className="font-medium text-gray-900 mb-1">1️⃣ Upload your resume (PDF or Word)</h2>
          <p className="text-xs text-gray-500 mb-3">One file only — keeps answers grounded in a single, consistent resume.</p>
          <input
            type="file"
            accept=".pdf,.docx,.doc"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="block w-full text-sm text-gray-700 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-accent file:text-white file:text-sm hover:file:brightness-110"
          />
        </section>

        <section className="mb-8">
          <h2 className="font-medium text-gray-900 mb-3">2️⃣ What level are you interviewing for?</h2>
          <div className="flex flex-wrap gap-2">
            {LEVELS.map((l) => (
              <button
                key={l}
                type="button"
                onClick={() => setLevel(l)}
                className={`px-4 py-1.5 rounded-full text-sm border transition ${
                  level === l ? "bg-accent text-white border-accent" : "border-gray-300 text-gray-700"
                }`}
              >
                {l}
              </button>
            ))}
          </div>
        </section>

        <section className="mb-8">
          <h2 className="font-medium text-gray-900 mb-1">3️⃣ What do you want to work on?</h2>
          <p className="text-xs text-gray-500 mb-4">Pick as many as you like — you can switch sections anytime from the sidebar.</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {SECTIONS.map((s) => {
              const checked = picked.includes(s.label);
              const [icon, ...nameParts] = s.label.split(" ");
              return (
                <button
                  key={s.key}
                  type="button"
                  disabled={!s.enabled}
                  onClick={() => togglePick(s.label)}
                  className={`text-left border rounded-xl p-3 transition disabled:opacity-40 disabled:cursor-not-allowed ${
                    checked ? "border-accent ring-1 ring-accent/30" : "border-gray-200"
                  }`}
                >
                  <div className="text-2xl text-center mb-1">{icon}</div>
                  <div className="text-sm font-medium text-center">{nameParts.join(" ")}</div>
                  <div className="text-xs text-gray-500 text-center mt-1">{s.desc}</div>
                  {!s.enabled && <div className="text-[10px] text-gray-400 text-center mt-1">Coming soon</div>}
                </button>
              );
            })}
          </div>
        </section>

        {error && <p className="text-sm text-red-600 mb-4">{error}</p>}

        <button
          type="button"
          onClick={handleSubmit}
          disabled={busy}
          className="w-full bg-accent text-white rounded-lg py-2.5 text-sm font-medium hover:brightness-110 transition disabled:opacity-60"
        >
          {busy ? "📄 Processing your resume..." : "🚀 Get Started"}
        </button>
      </div>
    </div>
  );
}
