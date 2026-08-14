import { useState, useEffect, useMemo } from "react";

// ChatGPT-style saved-chats rail: "+ New chat", a search box, and a list of past sessions for
// this section, grouped by when they were last updated (Today / Yesterday / Earlier). Clicking
// a saved chat loads it straight from the database (see the page's onSelect handler) - no LLM
// call, so revisiting something you already asked costs zero tokens. Search matches the chat
// title, every question asked, and every generated answer - also no LLM call, just a plain
// substring match on the backend, so searching is free too.
//
// Responsive: self-contained, so every page that already renders <ChatHistoryPanel /> gets this
// for free with no changes needed there. Below the `lg` breakpoint the panel is hidden by
// default and opens as a slide-out drawer via its own small floating toggle button, instead of
// permanently eating a fixed column of a phone-width screen. At `lg`+ it's a normal static
// column, same as before.
export default function ChatHistoryPanel({ sessions, activeSessionId, onNewChat, onSelect, onDelete, onRename, onSearch }) {
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState("");
  const [query, setQuery] = useState("");
  const [mobileOpen, setMobileOpen] = useState(false);

  // Debounced so typing doesn't fire a request per keystroke.
  useEffect(() => {
    if (!onSearch) return;
    const timer = setTimeout(() => onSearch(query), 250);
    return () => clearTimeout(timer);
  }, [query, onSearch]);

  const groups = useMemo(() => groupByDate(sessions), [sessions]);

  function startRename(s) {
    setRenamingId(s.id);
    setRenameValue(s.title);
  }

  function commitRename() {
    if (renameValue.trim()) onRename(renamingId, renameValue.trim());
    setRenamingId(null);
  }

  // Closing after picking/starting a chat only matters on mobile (setMobileOpen has no visible
  // effect at `lg`+ since the drawer classes are forced open there regardless of state).
  function selectAndClose(id) {
    onSelect(id);
    setMobileOpen(false);
  }

  function newChatAndClose() {
    onNewChat();
    setMobileOpen(false);
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setMobileOpen(true)}
        aria-label="Open chat history"
        className="lg:hidden fixed bottom-4 left-4 z-30 w-11 h-11 rounded-full bg-white border border-gray-200 shadow-md text-lg flex items-center justify-center"
      >
        🕘
      </button>
      {mobileOpen && (
        <div className="fixed inset-0 bg-black/30 z-30 lg:hidden" onClick={() => setMobileOpen(false)} />
      )}
      <div
        className={`w-56 shrink-0 border-r border-gray-200 bg-white flex flex-col h-full
          fixed inset-y-0 left-0 z-40 transform transition-transform duration-200
          ${mobileOpen ? "translate-x-0" : "-translate-x-full"}
          lg:static lg:translate-x-0 lg:z-auto`}
      >
      <button
        type="button"
        onClick={newChatAndClose}
        className="mx-2 mt-2 text-sm font-medium border border-gray-300 rounded-lg py-2 hover:bg-gray-50 transition"
      >
        ➕ New chat
      </button>

      <div className="px-2 mt-2 mb-1">
        <div className="relative">
          <span className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-400 text-xs">🔍</span>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search chats"
            className="w-full text-xs border border-gray-300 rounded-lg pl-7 pr-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-accent/40"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-3">
        {sessions.length === 0 && (
          <p className="text-xs text-gray-400 px-2 py-2">
            {query ? "No chats match that search." : "No saved chats yet — ask something to start one."}
          </p>
        )}
        {groups.map(([label, items]) => (
          <div key={label}>
            <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide px-2 mb-1">{label}</p>
            <div className="space-y-1">
              {items.map((s) => (
                <SessionRow
                  key={s.id}
                  s={s}
                  active={s.id === activeSessionId}
                  renaming={renamingId === s.id}
                  renameValue={renameValue}
                  setRenameValue={setRenameValue}
                  onCommitRename={commitRename}
                  onCancelRename={() => setRenamingId(null)}
                  onStartRename={() => startRename(s)}
                  onSelect={() => selectAndClose(s.id)}
                  onDelete={() => onDelete(s.id)}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
      </div>
    </>
  );
}

function SessionRow({ s, active, renaming, renameValue, setRenameValue, onCommitRename, onCancelRename, onStartRename, onSelect, onDelete }) {
  return (
    <div
      className={`group rounded-lg px-2 py-1.5 cursor-pointer text-xs flex items-center justify-between gap-1 ${
        active ? "bg-accent/10 text-accent" : "text-gray-700 hover:bg-gray-50"
      }`}
      onClick={() => !renaming && onSelect()}
    >
      {renaming ? (
        <input
          autoFocus
          value={renameValue}
          onChange={(e) => setRenameValue(e.target.value)}
          onBlur={onCommitRename}
          onKeyDown={(e) => {
            if (e.key === "Enter") onCommitRename();
            if (e.key === "Escape") onCancelRename();
          }}
          onClick={(e) => e.stopPropagation()}
          className="flex-1 text-xs border border-gray-300 rounded px-1 py-0.5"
        />
      ) : (
        <>
          <span className="truncate flex-1" title={s.title}>{s.title}</span>
          <span className="hidden group-hover:flex gap-1 shrink-0">
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onStartRename(); }}
              className="text-gray-400 hover:text-gray-700"
              title="Rename"
            >
              ✏️
            </button>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onDelete(); }}
              className="text-gray-400 hover:text-red-600"
              title="Delete"
            >
              🗑️
            </button>
          </span>
        </>
      )}
    </div>
  );
}

// Groups sessions (already sorted newest-first by the backend) into Today / Yesterday / Earlier
// this month / Older buckets based on updated_at, purely for display - no change to ordering.
function groupByDate(sessions) {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfYesterday = new Date(startOfToday);
  startOfYesterday.setDate(startOfYesterday.getDate() - 1);
  const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);

  const buckets = { Today: [], Yesterday: [], "Earlier this month": [], Older: [] };
  for (const s of sessions) {
    const updated = new Date(s.updated_at);
    if (updated >= startOfToday) buckets.Today.push(s);
    else if (updated >= startOfYesterday) buckets.Yesterday.push(s);
    else if (updated >= startOfMonth) buckets["Earlier this month"].push(s);
    else buckets.Older.push(s);
  }
  return Object.entries(buckets).filter(([, items]) => items.length > 0);
}
