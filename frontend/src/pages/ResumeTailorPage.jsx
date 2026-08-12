import { useEffect, useState } from "react";
import * as api from "../api/client";
import { useProvider } from "../context/ProviderContext";
import TruncationBanner from "../components/TruncationBanner";

// Mirrors src/resume_tailor_ui.py: paste a JD, get suggested bullets to ADD (never rewrites
// existing text) for your first two projects, plus a live ATS keyword score that updates the
// instant you check/uncheck a suggestion - nothing changes in the actual resume until you
// approve it.
export default function ResumeTailorPage() {
  const { provider } = useProvider();
  const [jdText, setJdText] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState("");

  const [fullResumeText, setFullResumeText] = useState("");
  const [jdKeywords, setJdKeywords] = useState([]);
  const [baselineScore, setBaselineScore] = useState(0);
  const [projects, setProjects] = useState(null); // [{original, suggestions, has_any_metric, missing_skills}]
  const [truncated, setTruncated] = useState(false);
  const [approvedSuggestions, setApprovedSuggestions] = useState([]); // [Set<int>]
  const [approvedSkills, setApprovedSkills] = useState([]); // [Set<int>]

  const [diffs, setDiffs] = useState(null); // [{final_snippet, left_html, right_html}]
  const [score, setScore] = useState(0);
  const [missing, setMissing] = useState([]);
  const [recomputing, setRecomputing] = useState(false);

  const [previewMarkdown, setPreviewMarkdown] = useState(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [downloadBusy, setDownloadBusy] = useState(false);

  async function handleAnalyze() {
    if (!jdText.trim()) {
      setError("Please paste a job description first.");
      return;
    }
    setError("");
    setAnalyzing(true);
    setPreviewMarkdown(null);
    try {
      const data = await api.analyzeResumeTailor(jdText, provider);
      setFullResumeText(data.full_resume_text);
      setJdKeywords(data.jd_keywords);
      setBaselineScore(data.baseline_score);
      setProjects(data.projects);
      setTruncated(data.truncated);
      setApprovedSuggestions(data.projects.map(() => new Set()));
      setApprovedSkills(data.projects.map(() => new Set()));
    } catch (err) {
      setError(err.message || "Couldn't parse a result — try again.");
    } finally {
      setAnalyzing(false);
    }
  }

  // Recompute (pure Python, no LLM call) every time a checkbox changes.
  useEffect(() => {
    if (!projects) return;
    let cancelled = false;
    setRecomputing(true);
    const projectStates = projects.map((proj, idx) => {
      const bullets = [
        ...[...approvedSuggestions[idx]].sort((a, b) => a - b).map((i) => proj.suggestions[i]),
        ...[...approvedSkills[idx]].sort((a, b) => a - b).map((i) => proj.missing_skills[i]?.draft),
      ].filter(Boolean);
      return { original: proj.original, approved_bullets: bullets };
    });
    api
      .recomputeResumeTailor({ fullResumeText, jdKeywords, projects: projectStates })
      .then((data) => {
        if (cancelled) return;
        setDiffs(data.diffs);
        setScore(data.score);
        setMissing(data.missing);
      })
      .catch((err) => !cancelled && setError(err.message || "Something went wrong."))
      .finally(() => !cancelled && setRecomputing(false));
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projects, approvedSuggestions, approvedSkills, fullResumeText, jdKeywords]);

  function toggleSuggestion(projectIdx, suggestionIdx) {
    setApprovedSuggestions((prev) => {
      const next = prev.map((s) => new Set(s));
      if (next[projectIdx].has(suggestionIdx)) next[projectIdx].delete(suggestionIdx);
      else next[projectIdx].add(suggestionIdx);
      return next;
    });
  }

  function toggleSkill(projectIdx, skillIdx) {
    setApprovedSkills((prev) => {
      const next = prev.map((s) => new Set(s));
      if (next[projectIdx].has(skillIdx)) next[projectIdx].delete(skillIdx);
      else next[projectIdx].add(skillIdx);
      return next;
    });
  }

  async function handlePreview() {
    if (!diffs) return;
    setPreviewBusy(true);
    setError("");
    try {
      const replacements = projects.map((proj, idx) => ({ original: proj.original, final: diffs[idx].final_snippet }));
      const data = await api.previewResumeTailor({ fullResumeText, replacements });
      setPreviewMarkdown(data.markdown);
    } catch (err) {
      setError(err.message || "Something went wrong.");
    } finally {
      setPreviewBusy(false);
    }
  }

  async function handleDownload() {
    if (!diffs) return;
    setDownloadBusy(true);
    setError("");
    try {
      const replacements = projects.map((proj, idx) => ({ original: proj.original, final: diffs[idx].final_snippet }));
      const blob = await api.downloadResumeTailor({ fullResumeText, replacements });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "tailored_resume.docx";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message || "Something went wrong.");
    } finally {
      setDownloadBusy(false);
    }
  }

  const delta = score - baselineScore;

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-xl font-medium text-gray-900 mb-1">🎯 Resume Tailor</h1>
      <p className="text-sm text-gray-500 mb-4">
        Paste a job description — for your first two projects, this suggests new points you
        could add to match it. Nothing changes until you check a box — your existing resume
        text is never rewritten or touched, only added to if you approve it.
      </p>

      <textarea
        value={jdText}
        onChange={(e) => setJdText(e.target.value)}
        placeholder="Paste JD text..."
        rows={7}
        className="w-full border border-gray-300 rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
      />
      <button
        type="button"
        onClick={handleAnalyze}
        disabled={analyzing}
        className="w-full mt-3 bg-accent text-white rounded-lg py-2.5 text-sm font-medium hover:brightness-110 transition disabled:opacity-60"
      >
        {analyzing ? "🔍 Matching your first two projects against this JD..." : "🎯 Analyze & Suggest"}
      </button>

      {error && <p className="text-sm text-red-600 mt-4">{error}</p>}

      {projects && (
        <>
          {truncated && <TruncationBanner />}
          <p className="text-sm text-emerald-700 mt-6 mb-4">✅ Found {projects.length} project(s)</p>

          {/* Live ATS score */}
          <div className="border border-gray-200 rounded-xl p-4 mb-6">
            <div className="flex items-center gap-4">
              <div>
                <p className="text-xs text-gray-500">🎯 ATS Match Score</p>
                <p className="text-2xl font-bold text-gray-900">
                  {score}%
                  {delta !== 0 && (
                    <span className={`text-sm ml-2 font-medium ${delta > 0 ? "text-emerald-600" : "text-red-500"}`}>
                      {delta > 0 ? "+" : ""}{delta}%
                    </span>
                  )}
                </p>
              </div>
              <div className="flex-1">
                <div className="w-full h-2 rounded-full bg-gray-200 overflow-hidden">
                  <div className="h-full bg-accent transition-all" style={{ width: `${Math.min(score, 100)}%` }} />
                </div>
                <p className="text-xs text-gray-500 mt-1">
                  {missing.length === 0
                    ? "✅ All detected JD keywords are present in your resume."
                    : `🔎 Missing from your resume (${missing.length}): ${missing.slice(0, 12).join(", ")}${missing.length > 12 ? "..." : ""}`}
                </p>
              </div>
            </div>
            {recomputing && <p className="text-[10px] text-gray-400 mt-2">Recalculating...</p>}
          </div>

          {projects.map((proj, idx) => (
            <ProjectBlock
              key={idx}
              index={idx}
              project={proj}
              approvedSuggestions={approvedSuggestions[idx]}
              approvedSkills={approvedSkills[idx]}
              onToggleSuggestion={(sIdx) => toggleSuggestion(idx, sIdx)}
              onToggleSkill={(sIdx) => toggleSkill(idx, sIdx)}
              diff={diffs?.[idx]}
            />
          ))}

          <button
            type="button"
            onClick={handlePreview}
            disabled={previewBusy || !diffs}
            className="w-full mt-2 bg-accent text-white rounded-lg py-2.5 text-sm font-medium hover:brightness-110 transition disabled:opacity-60"
          >
            {previewBusy ? "Building preview..." : "👁️ Preview Tailored Resume"}
          </button>

          {previewMarkdown && (
            <div className="mt-4">
              <p className="text-sm font-medium text-gray-900 mb-2">
                📄 Preview — this is the structure/formatting the downloaded .docx will have:
              </p>
              <div className="border border-gray-200 rounded-xl p-4 bg-white">
                <MarkdownLite text={previewMarkdown} />
              </div>
              <button
                type="button"
                onClick={handleDownload}
                disabled={downloadBusy}
                className="w-full mt-3 border border-gray-300 rounded-lg py-2.5 text-sm font-medium hover:bg-gray-50 transition disabled:opacity-60"
              >
                {downloadBusy ? "Preparing file..." : "⬇️ Download Tailored Resume (.docx)"}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ProjectBlock({ index, project, approvedSuggestions, approvedSkills, onToggleSuggestion, onToggleSkill, diff }) {
  return (
    <div className="mb-6">
      <h2 className="text-sm font-semibold text-gray-900 mb-2">📁 Project {index + 1}</h2>

      {project.suggestions.length > 0 ? (
        <div className="mb-2">
          <p className="text-xs font-medium text-gray-700 mb-1.5">💡 Suggested points to add — check any that are actually true:</p>
          <div className="space-y-1.5">
            {project.suggestions.map((s, sIdx) => (
              <label key={sIdx} className="flex items-start gap-2 text-sm text-gray-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={approvedSuggestions.has(sIdx)}
                  onChange={() => onToggleSuggestion(sIdx)}
                  className="mt-0.5"
                />
                <span>{s}</span>
              </label>
            ))}
          </div>
        </div>
      ) : (
        <p className="text-xs text-gray-400 mb-2">No suggestions generated for this project.</p>
      )}

      <p className="text-xs text-gray-400 mb-3">
        {project.has_any_metric
          ? "📊 One or more suggestions above include an illustrative estimated metric — verify it's roughly accurate before including, or edit it to your real number."
          : "📊 No quantitative metric applicable for this project's suggestions."}
      </p>

      {project.missing_skills.length > 0 && (
        <div className="mb-3">
          <p className="text-xs font-medium text-gray-700 mb-1">🚧 Skills this JD wants that aren't on your resume:</p>
          <p className="text-[11px] text-gray-400 mb-2">
            These are real gaps — not something to fake. Where a plausible, honest tie-in to your
            actual work exists, we draft a bullet for it below; check it in only at your own
            risk, and only if it's genuinely true.
          </p>
          <div className="space-y-2">
            {project.missing_skills.map((item, skIdx) => (
              <div key={skIdx}>
                <div className="border border-amber-300 bg-amber-50 rounded-lg px-3 py-1.5 text-xs text-amber-800 mb-1">
                  🚧 <strong>{item.skill}</strong> — {item.note}
                </div>
                {!item.draft.toLowerCase().includes("no plausible tie-in") && (
                  <label className="flex items-start gap-2 text-sm text-gray-700 cursor-pointer pl-1">
                    <input
                      type="checkbox"
                      checked={approvedSkills.has(skIdx)}
                      onChange={() => onToggleSkill(skIdx)}
                      className="mt-0.5"
                    />
                    <span>💡 {item.draft}</span>
                  </label>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <p className="text-xs text-gray-400 mb-2">Side-by-side diff — stays identical until you check a box above, then updates live:</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <p className="text-xs font-medium text-gray-700 mb-1">Before</p>
          <div className="border border-gray-200 rounded-lg p-3 bg-white text-sm" dangerouslySetInnerHTML={{ __html: diff?.left_html || "" }} />
        </div>
        <div>
          <p className="text-xs font-medium text-gray-700 mb-1">After</p>
          <div className="border border-gray-200 rounded-lg p-3 bg-white text-sm" dangerouslySetInnerHTML={{ __html: diff?.right_html || "" }} />
        </div>
      </div>
      <hr className="mt-6 border-gray-100" />
    </div>
  );
}

// Tiny markdown-lite renderer for the backend's plain-text preview (### headers, **bold**
// lines, - bullets, indented sub-bullets) - avoids pulling in a full markdown library for a
// handful of patterns the backend actually produces.
function MarkdownLite({ text }) {
  const lines = text.split("\n");
  return (
    <div className="space-y-1">
      {lines.map((line, i) => {
        const trimmed = line.trim();
        if (!trimmed) return <div key={i} className="h-2" />;
        if (trimmed.startsWith("### ")) {
          return <h3 key={i} className="text-base font-bold text-gray-900 mt-2">{trimmed.slice(4)}</h3>;
        }
        if (trimmed.startsWith("**") && trimmed.endsWith("**")) {
          return <p key={i} className="text-sm font-bold text-gray-900 mt-3">{trimmed.slice(2, -2)}</p>;
        }
        if (trimmed.startsWith("*") && trimmed.endsWith("*")) {
          return <p key={i} className="text-xs italic text-gray-500">{trimmed.slice(1, -1)}</p>;
        }
        if (line.startsWith("    - ")) {
          return <p key={i} className="text-sm text-gray-700 pl-8">◦ {trimmed.slice(2)}</p>;
        }
        if (trimmed.startsWith("- ")) {
          return <p key={i} className="text-sm text-gray-700 pl-4">• {trimmed.slice(2)}</p>;
        }
        if (trimmed === "---") {
          return <hr key={i} className="my-3 border-gray-100" />;
        }
        return <p key={i} className="text-sm text-gray-700">{trimmed}</p>;
      })}
    </div>
  );
}
