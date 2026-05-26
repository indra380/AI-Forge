import { useState } from "react";

import type { ChatThread } from "../../types";

interface Props {
  threads: ChatThread[];
  activeThreadId: string | null;
  onSelect: (thread: ChatThread) => void;
  onNew: () => void;
  onRename: (threadId: string, title: string) => void;
  onDelete: (threadId: string) => void;
}

export function ThreadSidebar({
  threads,
  activeThreadId,
  onSelect,
  onNew,
  onRename,
  onDelete,
}: Props) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");

  function startEdit(thread: ChatThread) {
    setEditingId(thread.id);
    setEditValue(thread.title);
  }

  function commitEdit(threadId: string) {
    const trimmed = editValue.trim();
    if (trimmed) onRename(threadId, trimmed);
    setEditingId(null);
  }

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
        <span className="text-sm font-semibold text-slate-800">Chats</span>
        <button
          type="button"
          onClick={onNew}
          className="rounded-lg bg-slate-900 px-3 py-1 text-xs font-medium text-white hover:bg-slate-700"
        >
          + New
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto py-2">
        {threads.length === 0 ? (
          <p className="px-4 py-3 text-xs text-slate-400">No chats yet. Start a new one!</p>
        ) : (
          threads.map((thread) => (
            <div
              key={thread.id}
              className={`group flex items-center gap-1 px-3 py-2 cursor-pointer rounded-lg mx-1 ${
                thread.id === activeThreadId
                  ? "bg-slate-100 text-slate-900"
                  : "text-slate-600 hover:bg-slate-50"
              }`}
              onClick={() => onSelect(thread)}
            >
              {editingId === thread.id ? (
                <input
                  autoFocus
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  onBlur={() => commitEdit(thread.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitEdit(thread.id);
                    if (e.key === "Escape") setEditingId(null);
                  }}
                  onClick={(e) => e.stopPropagation()}
                  className="flex-1 rounded border border-slate-300 px-1 py-0.5 text-xs outline-none"
                />
              ) : (
                <span className="flex-1 truncate text-sm">{thread.title}</span>
              )}

              <span className="hidden shrink-0 group-hover:flex gap-0.5">
                <button
                  type="button"
                  title="Rename"
                  onClick={(e) => {
                    e.stopPropagation();
                    startEdit(thread);
                  }}
                  className="rounded p-0.5 text-slate-400 hover:text-slate-700"
                >
                  ✎
                </button>
                <button
                  type="button"
                  title="Delete"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(thread.id);
                  }}
                  className="rounded p-0.5 text-slate-400 hover:text-red-600"
                >
                  ✕
                </button>
              </span>
            </div>
          ))
        )}
      </nav>
    </aside>
  );
}
