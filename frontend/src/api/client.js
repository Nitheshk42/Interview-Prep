const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

function authHeaders() {
  const token = localStorage.getItem("studysager_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function handle(res) {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // ignore - no JSON body
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function signup(username, email, password) {
  const res = await fetch(`${API_URL}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, email, password }),
  });
  return handle(res);
}

export async function login(username, password) {
  const res = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  return handle(res);
}

export async function me() {
  const res = await fetch(`${API_URL}/auth/me`, { headers: authHeaders() });
  return handle(res);
}

export async function completeOnboarding(resumeFile, level, favoriteTabs) {
  const form = new FormData();
  form.append("resume", resumeFile);
  form.append("level", level);
  form.append("favorite_tabs", favoriteTabs.join("|"));
  const res = await fetch(`${API_URL}/onboarding/complete`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  return handle(res);
}

export async function reprocessResume(resumeFile) {
  const form = new FormData();
  form.append("resume", resumeFile);
  const res = await fetch(`${API_URL}/onboarding/reprocess-resume`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  return handle(res);
}

export async function askChat(question, provider = "groq") {
  const res = await fetch(`${API_URL}/chat/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ question, provider }),
  });
  return handle(res);
}

export async function askHybridChat(question, provider = "groq") {
  const res = await fetch(`${API_URL}/hybrid-chat/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ question, provider }),
  });
  return handle(res);
}

export async function askLevelChat(question, provider = "groq") {
  const res = await fetch(`${API_URL}/level-chat/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ question, provider }),
  });
  return handle(res);
}

// ===== Saved chat sessions (ChatGPT-style history) - shared by Chat Assistant, Hybrid Chat,
// and EXP Level Answers. Reopening a session via getSession() never calls the LLM - it just
// replays what's already stored, so it costs zero tokens compared to re-asking. =====

export async function listSessions(section) {
  const res = await fetch(`${API_URL}/sessions?section=${encodeURIComponent(section)}`, {
    headers: authHeaders(),
  });
  return handle(res);
}

export async function createSession(section, title) {
  const res = await fetch(`${API_URL}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ section, title }),
  });
  return handle(res);
}

export async function getSession(sessionId) {
  const res = await fetch(`${API_URL}/sessions/${sessionId}`, { headers: authHeaders() });
  return handle(res);
}

export async function appendSessionMessage(sessionId, question, response) {
  const res = await fetch(`${API_URL}/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ question, response }),
  });
  return handle(res);
}

export async function renameSession(sessionId, title) {
  const res = await fetch(`${API_URL}/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ title }),
  });
  return handle(res);
}

export async function deleteSession(sessionId) {
  const res = await fetch(`${API_URL}/sessions/${sessionId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  return handle(res);
}

// ===== Resume Sync: tool-by-tool experience breakdown, and vendor JD screening prep =====

export async function generateToolBreakdown(provider = "groq") {
  const res = await fetch(`${API_URL}/resume-sync/tool-breakdown`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ provider }),
  });
  return handle(res);
}

export async function generateVendorQa({ jdText, provider = "groq", numQuestions = 8 }) {
  const res = await fetch(`${API_URL}/resume-sync/vendor-qa`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ jd_text: jdText, provider, num_questions: numQuestions }),
  });
  return handle(res);
}

export async function generateJdQuestions({ jdText, provider = "groq", numQuestions = 5, excludeQuestions = [], checkAlignment = true }) {
  const res = await fetch(`${API_URL}/jd-chat/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      jd_text: jdText, provider, num_questions: numQuestions,
      exclude_questions: excludeQuestions, check_alignment: checkAlignment,
    }),
  });
  return handle(res);
}

export async function generateGeneralJdQuestions({ jdText, provider = "groq", numQuestions = 6, excludeQuestions = [] }) {
  const res = await fetch(`${API_URL}/general-jd-chat/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ jd_text: jdText, provider, num_questions: numQuestions, exclude_questions: excludeQuestions }),
  });
  return handle(res);
}

export async function analyzeResumeTailor(jdText, provider = "groq") {
  const res = await fetch(`${API_URL}/resume-tailor/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ jd_text: jdText, provider }),
  });
  return handle(res);
}

export async function recomputeResumeTailor({ fullResumeText, jdKeywords, projects }) {
  const res = await fetch(`${API_URL}/resume-tailor/recompute`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ full_resume_text: fullResumeText, jd_keywords: jdKeywords, projects }),
  });
  return handle(res);
}

export async function previewResumeTailor({ fullResumeText, replacements }) {
  const res = await fetch(`${API_URL}/resume-tailor/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ full_resume_text: fullResumeText, replacements }),
  });
  return handle(res);
}

export async function downloadResumeTailor({ fullResumeText, replacements }) {
  const res = await fetch(`${API_URL}/resume-tailor/download`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ full_resume_text: fullResumeText, replacements }),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return res.blob();
}
