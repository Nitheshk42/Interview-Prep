// Mirrors src/sections.py in the Streamlit app - single source of truth for the app's
// navigable sections. Only "Chat Assistant" has a real page/backend route so far; the rest
// are listed so the onboarding picker and sidebar nav match the target app shape, and will
// light up as each section is ported over.
//
// `phase` groups sections in the sidebar by when you'd actually use them: "before" = prep work
// done ahead of time (practice answers, tailor your resume, generate likely questions),
// "during" = fast lookup you'd realistically reach for mid-interview (Hybrid Chat). Sections
// with phase: null (Visual RAG Learning) are shown ungrouped, at the end.
export const SECTIONS = [
  { key: "resume_sync", label: "🎯 Resume Sync", desc: "Tool-by-tool experience sync + vendor call prep", enabled: true, phase: "before" },
  { key: "chat", label: "💬 Chat Assistant", desc: "Ask anything about your resume", enabled: true, phase: "before" },
  { key: "level", label: "🪜 My EXP Level Answers", desc: "Same question, every seniority level", enabled: true, phase: "before" },
  { key: "jd", label: "📋 My JD Answers", desc: "Interview Q&A matched to your resume", enabled: true, phase: "before" },
  { key: "general_jd", label: "🧠 General JD Answers", desc: "Interview Q&A with no resume context", enabled: true, phase: "before" },
  { key: "tailor", label: "🎯 Resume Tailor", desc: "Tailor your bullets to a job description", enabled: true, phase: "before" },
  { key: "hybrid", label: "🔀 Hybrid Chat", desc: "Resume facts plus technical depth", enabled: true, phase: "during" },
  { key: "visual", label: "📖 Visual RAG Learning", desc: "See how your resume becomes searchable", enabled: false, phase: null },
];

export const PHASE_LABELS = {
  before: "🗂️ Before Interview",
  during: "🎤 During Interview",
};

export const DEFAULT_SECTION = "chat";
