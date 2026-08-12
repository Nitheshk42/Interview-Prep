import { useState } from "react";

// ChatGPT-style saved-chats rail: "+ New chat" plus a list of past sessions for this section.
// Clicking a saved chat loads it straight from the database (see the page's onSelect handler) -
// no LLM call, so revisiting something you already asked costs zero tokens.
export default function ChatHistoryPanel({ sessions, activeSessionId, onNewChat, onSelect, onDelete, onRename }) {
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState("");

  function startRename(s) {
    setRenamingId(s.id);
    setRenameValue(s.title);
  }

  function commitRename() {
    if (renameValue.trim()) onRename(renamingId, renameValue.trim());
    setRenamingId(null);
  }

  return (
    <div className="w-56 shrink-0 border-r border-gray-200 flex flex-col h-full">
      <button
        type="button"
        onClick={onNewChat}
        className="m-2 text-sm font-medium border border-gray-300 rounded-lg py-2 hover:bg-gray-50 transition"
      >
        ➕ New chat
      </button>
      <div className="flex-1 overflow-y-auto px-2 space-y-1">
        {sessions.length === 0 && (
          <p className="text-xs text-gray-400 px-2 py-2">No saved chats yet — ask something to start one.</p>
        )}
        {sessions.map((s) => (
          <div
            key={s.id}
            className={`group rounded-lg px-2 py-1.5 cursor-pointer text-xs flex items-center justify-between gap-1 ${
              s.id === activeSessionId ? "bg-accent/10 text-accent" : "text-gray-700 hover:bg-gray-50"
            }`}
            onClick={() => renamingId !== s.id && onSelect(s.id)}
          >
            {renamingId === s.id ? (
              <input
                autoFocus
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                onBlur={commitRename}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commitRename();
                  if (e.key === "Escape") setRenamingId(null);
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
                    onClick={(e) => { e.stopPropagation(); startRename(s); }}
                    className="text-gray-400 hover:text-gray-700"
                    title="Rename"
                  >
                    ✏️
                  </button>
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); onDelete(s.id); }}
                    className="text-gray-400 hover:text-red-600"
                    title="Delete"
                  >
                    🗑️
                  </button>
                </span>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
