import { useState, useEffect, useCallback, useRef } from "react";
import * as api from "../api/client";
import { useProvider } from "../context/ProviderContext";
import MicButton from "../components/MicButton";
import ChatHistoryPanel from "../components/ChatHistoryPanel";
import TruncationBanner from "../components/TruncationBanner";

const SECTION = "chat";

// Mirrors src/chat.py: a chat panel plus an "LLM reasoning" side panel. The side panel walks
// through the actual RAG pipeline in order - retrieve chunks, build the prompt from them,
// generate the answer - so it's clear the answer isn't the LLM's general knowledge, it's
// grounded in specific chunks pulled from the resume.
//
// Saved chats: a ChatGPT-style history rail on the left lets you reopen a past conversation.
// Reopening replays the stored answers straight from the database - no LLM call, so it costs
// zero tokens, unlike re-asking the same question.
export default function ChatPage() {
  const { provider } = useProvider();
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [lastResult, setLastResult] = useState(null); // { retrieved, context, prompt, answer, question }
  const [showFullPrompt, setShowFullPrompt] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef(null);

  // Jump straight to the newest question/answer whenever the thread changes, instead of
  // leaving the user to scroll down and hunt for what they just asked.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const refreshSessions = useCallback(() => {
    api.listSessions(SECTION).then(setSessions).catch(() => {});
  }, []);

  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  function handleNewChat() {
    setActiveSessionId(null);
    setMessages([]);
    setLastResult(null);
    setShowFullPrompt(false);
    setError("");
  }

  async function handleSelectSession(sessionId) {
    setError("");
    try {
      const session = await api.getSession(sessionId);
      setActiveSessionId(sessionId);
      const turns = session.messages;
      setMessages(
        turns.flatMap((t) => [
          { role: "user", content: t.question },
          { role: "assistant", content: t.response.answer },
        ])
      );
      const last = turns[turns.length - 1];
      setLastResult(last ? { ...last.response, question: last.question } : null);
      setShowFullPrompt(false);
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
    setMessages((m) => [...m, { role: "user", content: question }]);
    setBusy(true);
    try {
      const data = await api.askChat(question, provider);
      setMessages((m) => [...m, { role: "assistant", content: data.answer }]);
      setLastResult({ ...data, question });
      setShowFullPrompt(false);

      // Persist this turn - create a session on the first question of a fresh chat, otherwise
      // append to the one already open.
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
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 p-6 max-w-6xl mx-auto flex-1 h-[calc(100vh-2rem)]">
        <div className="lg:col-span-2 flex flex-col h-full min-h-0">
        <h1 className="text-xl font-medium text-gray-900 mb-1 shrink-0">💬 StudySage Chat</h1>
        <p className="text-sm text-gray-500 mb-4 shrink-0">Ask questions about your processed resume</p>

        {/* Message list is the only thing that scrolls - the input bar below stays pinned at
            the bottom of the panel instead of drifting wherever the page happens to end. */}
        <div className="flex-1 min-h-0 border border-gray-200 rounded-xl p-4 space-y-3 overflow-y-auto bg-white">
          {messages.length === 0 && (
            <p className="text-sm text-gray-400">Ask anything about your resume to get started.</p>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[80%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap ${
                  m.role === "user" ? "bg-accent text-white" : "bg-gray-100 text-gray-800"
                }`}
              >
                {m.content}
              </div>
            </div>
          ))}
          {busy && <p className="text-sm text-gray-400">🔍 Processing...</p>}
          {!busy && lastResult?.truncated && <TruncationBanner variant="single" compact />}
          <div ref={bottomRef} />
        </div>

        {error && <p className="text-sm text-red-600 mt-2 shrink-0">{error}</p>}

        <form onSubmit={handleSend} className="mt-3 flex gap-2 shrink-0">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask anything about your documents..."
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

      <div className="h-full overflow-y-auto">
        <h2 className="text-sm font-medium text-gray-900 mb-1">🤖 How this answer was generated</h2>
        {!lastResult ? (
          <p className="text-sm text-gray-400 mt-2">💭 Ask a question to see the pipeline here...</p>
        ) : (
          <div className="space-y-4 mt-3">
            <p className="text-xs text-gray-500 leading-relaxed">
              The LLM never "just knows" the answer — every response below is built in three
              steps, in order. It only ever sees the chunks retrieved in Step 1, so anything it
              says should trace back to something in there.
            </p>

            {/* Step 1: retrieval */}
            <StepCard number={1} title="Search your resume" accent>
              {lastResult.full_resume_used ? (
                <p className="text-xs text-gray-500 mb-2">
                  This question asked for a full list/timeline, so a similarity-ranked search
                  wasn't used — <strong>every chunk of your resume</strong> was pulled in instead,
                  to make sure nothing gets left out.
                </p>
              ) : (
                <p className="text-xs text-gray-500 mb-2">
                  Your question was converted into a vector and compared against every chunk of
                  your resume. The <strong>closest matches</strong> below were pulled out — match %
                  is relative to each other (100% = best match found for this question, not an
                  absolute score).
                </p>
              )}
              <div className="space-y-2">
                {lastResult.retrieved.map((c, i) => (
                  <ChunkCard key={i} index={i} chunk={c} showMatch={!lastResult.full_resume_used} />
                ))}
              </div>
            </StepCard>

            {/* Step 2: prompt construction */}
            <StepCard number={2} title="Build the prompt">
              <p className="text-xs text-gray-500 mb-2">
                Those chunks were stitched together as "context," combined with grounding rules
                (stay specific, get recency right) and your question, into a single prompt.
              </p>
              <button
                type="button"
                onClick={() => setShowFullPrompt((v) => !v)}
                className="text-xs text-accent font-medium hover:underline"
              >
                {showFullPrompt ? "Hide the exact prompt sent ▲" : "Show the exact prompt sent ▼"}
              </button>
              {showFullPrompt && (
                <pre className="text-xs whitespace-pre-wrap text-gray-700 bg-gray-50 border border-gray-200 rounded-lg p-2 mt-2 max-h-64 overflow-y-auto">
                  {lastResult.prompt}
                </pre>
              )}
            </StepCard>

            {/* Step 3: generation */}
            <StepCard number={3} title="Generate the answer">
              <p className="text-xs text-gray-500 mb-2">
                The LLM reads that prompt and writes an answer grounded only in the context
                above — nothing from outside your resume.
              </p>
              <blockquote className="text-xs text-gray-700 border-l-2 border-accent pl-2 whitespace-pre-wrap">
                {lastResult.answer}
              </blockquote>
            </StepCard>
          </div>
        )}
      </div>
      </div>
    </div>
  );
}

function StepCard({ number, title, children }) {
  return (
    <div className="border border-gray-200 rounded-xl p-3 bg-white">
      <div className="flex items-center gap-2 mb-2">
        <span className="flex items-center justify-center w-5 h-5 rounded-full bg-accent text-white text-[11px] font-medium shrink-0">
          {number}
        </span>
        <h3 className="text-sm font-medium text-gray-900">{title}</h3>
      </div>
      {children}
    </div>
  );
}

function ChunkCard({ index, chunk, showMatch = true }) {
  const barColor =
    chunk.match_pct >= 66 ? "bg-emerald-500" : chunk.match_pct >= 33 ? "bg-amber-500" : "bg-gray-400";
  return (
    <details className="border border-gray-200 rounded-lg p-2 bg-gray-50" open={index === 0}>
      <summary className="cursor-pointer text-xs text-gray-600 flex items-center justify-between gap-2">
        <span>Chunk {index + 1}</span>
        {showMatch ? (
          <span className="flex items-center gap-2 shrink-0">
            <span className="w-16 h-1.5 rounded-full bg-gray-200 overflow-hidden">
              <span className={`block h-full ${barColor}`} style={{ width: `${chunk.match_pct}%` }} />
            </span>
            <span className="text-gray-500">{chunk.match_pct}% match</span>
          </span>
        ) : (
          <span className="text-gray-400 text-[10px]">included in full fetch</span>
        )}
      </summary>
      <pre className="text-xs whitespace-pre-wrap text-gray-700 mt-2">{chunk.content}</pre>
      {showMatch && (
        <p className="text-[10px] text-gray-400 mt-1">raw distance: {chunk.distance.toFixed(4)} (lower = closer)</p>
      )}
    </details>
  );
}
