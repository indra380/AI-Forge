import { useCallback, useRef, useState } from "react";
import type { DragEvent, FormEvent, KeyboardEvent } from "react";

import { deleteUploadedFile, uploadFile } from "../../lib/api";
import type { PendingFile } from "../../types";

const ACCEPTED_EXTENSIONS = new Set([
  ".pdf",
  ".png",
  ".jpg",
  ".jpeg",
  ".webp",
  ".gif",
  ".mp4",
  ".webm",
  ".mov",
  ".csv",
  ".xlsx",
  ".json",
  ".txt",
  ".md",
  ".py",
  ".js",
  ".ts",
  ".tsx",
  ".java",
  ".yml",
  ".yaml",
  ".sql",
  ".tex",
  ".docx",
]);

function getExtension(name: string): string {
  const idx = name.lastIndexOf(".");
  if (idx < 0) return "";
  return name.slice(idx).toLowerCase();
}

function isAcceptedFile(file: File): boolean {
  const extension = getExtension(file.name);
  return ACCEPTED_EXTENSIONS.has(extension);
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function FileCard({ pf, onRemove }: { pf: PendingFile; onRemove: () => void }) {
  const isPdf = pf.file.type === "application/pdf";
  return (
    <div className="relative flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs">
      {isPdf ? (
        <span className="text-lg">📄</span>
      ) : pf.previewUrl ? (
        <img src={pf.previewUrl} alt={pf.file.name} className="h-10 w-10 rounded object-cover" />
      ) : (
        <span className="text-lg">📎</span>
      )}
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-slate-700">{pf.file.name}</p>
        {pf.status === "uploading" ? (
          <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-slate-200">
            <div
              className="h-full bg-blue-500 transition-all"
              style={{ width: `${pf.progress}%` }}
            />
          </div>
        ) : pf.status === "error" ? (
          <p className="text-red-500">{pf.error ?? "Upload failed"}</p>
        ) : pf.uploaded?.isIndexed ? (
          <p className="text-green-600">Indexed ✓</p>
        ) : (
          <p className="text-slate-400">{formatSize(pf.file.size)}</p>
        )}
      </div>
      <button
        type="button"
        onClick={onRemove}
        className="ml-1 rounded-full p-0.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700"
        aria-label="Remove attachment"
      >
        ✕
      </button>
    </div>
  );
}

interface ChatInputBarProps {
  disabled: boolean;
  sessionId: string | null;
  onEnsureSession: () => string;
  onSend: (message: string, attachmentIds: string[]) => Promise<void>;
}

export function ChatInputBar({
  disabled,
  sessionId,
  onEnsureSession,
  onSend,
}: ChatInputBarProps) {
  const [value, setValue] = useState("");
  const [attachments, setAttachments] = useState<PendingFile[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  void sessionId;

  const addFiles = useCallback(
    (files: File[]) => {
      const sid = onEnsureSession();
      for (const file of files) {
        const isAccepted = isAcceptedFile(file);
        if (!isAccepted) continue;

        const localId = crypto.randomUUID();
        const previewUrl =
          file.type.startsWith("image/") ? URL.createObjectURL(file) : undefined;

        const pending: PendingFile = {
          id: localId,
          file,
          status: "uploading",
          progress: 0,
          previewUrl,
        };
        setAttachments((prev) => [...prev, pending]);

        uploadFile(sid, file, (pct) => {
          setAttachments((prev) =>
            prev.map((a) => (a.id === localId ? { ...a, progress: pct } : a))
          );
        })
          .then((uploaded) => {
            setAttachments((prev) =>
              prev.map((a) =>
                a.id === localId ? { ...a, status: "indexed", progress: 100, uploaded } : a
              )
            );
          })
          .catch((err: unknown) => {
            const msg = err instanceof Error ? err.message : "Upload failed";
            setAttachments((prev) =>
              prev.map((a) => (a.id === localId ? { ...a, status: "error", error: msg } : a))
            );
          });
      }
    },
    [onEnsureSession]
  );

  function handleFileInput() {
    const input = fileInputRef.current;
    if (!input?.files) return;
    addFiles(Array.from(input.files));
    input.value = "";
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    addFiles(Array.from(e.dataTransfer.files));
  }

  function handleDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(true);
  }

  function handlePaste(e: React.ClipboardEvent<HTMLTextAreaElement>) {
    const items = Array.from(e.clipboardData.items);
    const imageFiles: File[] = [];
    for (const item of items) {
      if (item.kind === "file" && item.type.startsWith("image/")) {
        const file = item.getAsFile();
        if (file) imageFiles.push(file);
      }
    }
    if (imageFiles.length > 0) addFiles(imageFiles);
  }

  async function handleRemove(pf: PendingFile) {
    const sid = sessionId ?? onEnsureSession();
    if (pf.uploaded?.fileId) {
      try {
        await deleteUploadedFile(pf.uploaded.fileId, sid);
      } catch {
        // best-effort cleanup
      }
    }
    if (pf.previewUrl) URL.revokeObjectURL(pf.previewUrl);
    setAttachments((prev) => prev.filter((a) => a.id !== pf.id));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = value.trim();
    const attachmentIds = attachments
      .filter((item) => item.status === "indexed" && item.uploaded?.fileId)
      .map((item) => item.uploaded!.fileId);

    if ((message.length === 0 && attachmentIds.length === 0) || disabled) return;

    const outgoingMessage = message.length > 0 ? message : "Please analyze the uploaded attachments.";

    setValue("");
    setAttachments([]);
    await onSend(outgoingMessage, attachmentIds);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      e.currentTarget.form?.dispatchEvent(
        new Event("submit", { bubbles: true, cancelable: true })
      );
    }
  }

  const uploading = attachments.some((a) => a.status === "uploading");

  return (
    <div className="border-t border-slate-200 bg-white px-4 py-3">
      <form onSubmit={handleSubmit}>
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={() => setDragOver(false)}
          className={`mx-auto w-full max-w-4xl rounded-2xl border transition ${
            dragOver
              ? "border-blue-400 bg-blue-50"
              : "border-slate-300 bg-white"
          }`}
        >
          {/* Attachment preview strip */}
          {attachments.length > 0 && (
            <div className="flex flex-wrap gap-2 px-3 pt-3">
              {attachments.map((pf) => (
                <FileCard key={pf.id} pf={pf} onRemove={() => handleRemove(pf)} />
              ))}
            </div>
          )}

          {/* Input row */}
          <div className="flex items-end gap-2 p-2">
            {/* Paperclip button */}
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="mb-1 rounded-full p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
              title="Attach files"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-5 w-5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"
                />
              </svg>
            </button>

            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,.webp,.gif,.mp4,.webm,.mov,.csv,.xlsx,.json,.txt,.md,.py,.js,.ts,.tsx,.java,.yml,.yaml,.sql,.tex,.docx"
              multiple
              className="hidden"
              onChange={handleFileInput}
            />

            <textarea
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
              placeholder={
                dragOver
                  ? "Drop files here…"
                  : "Ask anything… (Shift+Enter for new line)"
              }
              rows={3}
              className="flex-1 resize-none rounded-xl px-3 py-2 text-sm outline-none placeholder:text-slate-400"
            />

            <button
              type="submit"
              disabled={disabled || uploading || value.trim().length === 0}
              className="mb-1 rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {uploading ? "Uploading…" : disabled ? "Thinking…" : "Send"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
