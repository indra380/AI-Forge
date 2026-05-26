import { useRef, useState } from "react";
import type { DragEvent } from "react";

import type { RagCitation, RagDocument, RagResponse } from "../../types";

interface RagPdfPanelProps {
  disabled: boolean;
  sessionId: string | null;
  onEnsureSession: () => string;
  onUploadPdf: (sessionId: string, file: File) => Promise<RagDocument>;
  onAsk: (sessionId: string, documentId: string, message: string) => Promise<RagResponse>;
}

export function RagPdfPanel({
  disabled,
  sessionId,
  onEnsureSession,
  onUploadPdf,
  onAsk,
}: RagPdfPanelProps) {
  const [documents, setDocuments] = useState<RagDocument[]>([]);
  const [activeDocumentId, setActiveDocumentId] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [citations, setCitations] = useState<RagCitation[]>([]);
  const [isIndexing, setIsIndexing] = useState(false);
  const [isAsking, setIsAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);

  async function upload(file: File) {
    if (disabled) return;
    const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
    if (!isPdf) {
      setError("Only PDF files are supported for document chat.");
      return;
    }

    const resolvedSessionId = sessionId ?? onEnsureSession();
    setError(null);
    setIsIndexing(true);
    try {
      const doc = await onUploadPdf(resolvedSessionId, file);
      setDocuments((prev) => [doc, ...prev.filter((d) => d.documentId !== doc.documentId)]);
      setActiveDocumentId(doc.documentId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to index PDF");
    } finally {
      setIsIndexing(false);
    }
  }

  async function ask() {
    if (!activeDocumentId || !question.trim() || disabled) return;
    const resolvedSessionId = sessionId ?? onEnsureSession();
    setError(null);
    setIsAsking(true);
    try {
      const result = await onAsk(resolvedSessionId, activeDocumentId, question.trim());
      setAnswer(result.response);
      setCitations(result.citations);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to answer from PDF");
    } finally {
      setIsAsking(false);
    }
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragOver(false);
    const file = event.dataTransfer.files?.[0];
    if (file) {
      void upload(file);
    }
  }

  return (
    <section className="border-b border-slate-200/80 bg-white/70 px-5 py-4">
      <div className="mx-auto max-w-5xl rounded-2xl border border-slate-200 bg-slate-50/60 p-4">
        <input
          ref={fileRef}
          type="file"
          accept="application/pdf,.pdf"
          hidden
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) {
              void upload(file);
            }
            event.target.value = "";
          }}
        />

        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-bold text-slate-900">Chat With PDF (RAG)</h2>
            <p className="text-xs text-slate-500">Upload, index, and ask grounded questions with page citations.</p>
          </div>
          <button
            type="button"
            disabled={disabled || isIndexing}
            onClick={() => fileRef.current?.click()}
            className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-50"
          >
            {isIndexing ? "Indexing..." : "Upload PDF"}
          </button>
        </div>

        <div
          onDragOver={(event) => {
            event.preventDefault();
            setIsDragOver(true);
          }}
          onDragLeave={() => setIsDragOver(false)}
          onDrop={handleDrop}
          className={`mb-3 rounded-2xl border border-dashed p-3 text-xs ${
            isDragOver ? "border-teal-500 bg-teal-50 text-teal-700" : "border-slate-300 bg-white text-slate-500"
          }`}
        >
          Drag and drop a PDF here to index it.
        </div>

        {documents.length > 0 ? (
          <div className="mb-3 grid gap-2 md:grid-cols-2">
            {documents.map((doc) => (
              <button
                key={doc.documentId}
                type="button"
                onClick={() => setActiveDocumentId(doc.documentId)}
                className={`rounded-xl border px-3 py-2 text-left ${
                  activeDocumentId === doc.documentId
                    ? "border-teal-500 bg-teal-50"
                    : "border-slate-200 bg-white hover:bg-slate-50"
                }`}
              >
                <p className="truncate text-xs font-semibold text-slate-800">{doc.filename}</p>
                <p className="text-[11px] uppercase tracking-[0.16em] text-slate-400">{doc.status}</p>
              </button>
            ))}
          </div>
        ) : null}

        <div className="flex gap-2">
          <input
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask about this PDF"
            className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-500"
          />
          <button
            type="button"
            disabled={disabled || isAsking || !activeDocumentId || !question.trim()}
            onClick={() => void ask()}
            className="rounded-xl bg-slate-900 px-3 py-2 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {isAsking ? "Asking..." : "Ask"}
          </button>
        </div>

        {error ? <p className="mt-2 text-xs text-red-600">{error}</p> : null}

        {answer ? (
          <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3">
            <p className="text-sm text-slate-700">{answer}</p>
            {citations.length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-2">
                {citations.map((citation, index) => (
                  <span key={`${citation.filename}-${citation.page}-${index}`} className="rounded-full bg-slate-100 px-2 py-1 text-[11px] text-slate-600">
                    {citation.filename} p.{citation.page}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}
