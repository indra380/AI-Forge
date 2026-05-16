import { useCallback, useRef, useState } from "react";
import {
  connectGoogleSheet,
  deleteDataset,
  listDatasets,
  queryDataset,
  uploadDataset,
} from "../../lib/api";
import type { DataMessage, Dataset, DataUploadResponse } from "../../types";

// ── tiny helpers ──────────────────────────────────────────────────────────────

function shortId() {
  return Math.random().toString(36).slice(2, 10);
}

function fmtRows(n: number) {
  return n.toLocaleString();
}

// ── sub-components ────────────────────────────────────────────────────────────

function DatasetBadge({
  dataset,
  active,
  onSelect,
  onDelete,
}: {
  dataset: Dataset;
  active: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      className={`flex cursor-pointer items-start justify-between rounded-xl border p-3 transition-colors ${
        active
          ? "border-indigo-300 bg-indigo-50"
          : "border-slate-200 bg-white hover:bg-slate-50"
      }`}
      onClick={onSelect}
    >
      <div className="min-w-0 flex-1">
        <p
          className="truncate text-sm font-medium text-slate-800"
          title={dataset.filename}
        >
          {dataset.source_url ? "🔗 " : "📄 "}
          {dataset.filename}
        </p>
        <p className="mt-0.5 text-xs text-slate-400">
          {fmtRows(dataset.rows)} rows · {dataset.columns} cols ·{" "}
          {dataset.sheets.length > 1
            ? `${dataset.sheets.length} sheets`
            : dataset.sheets[0]}
        </p>
      </div>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        className="ml-2 shrink-0 text-slate-300 hover:text-red-500"
        title="Remove dataset"
      >
        ✕
      </button>
    </div>
  );
}

function MessageBubble({ msg }: { msg: DataMessage }) {
  const [codeCopied, setCodeCopied] = useState(false);

  function copyCode() {
    if (msg.code) {
      void navigator.clipboard.writeText(msg.code).then(() => {
        setCodeCopied(true);
        setTimeout(() => setCodeCopied(false), 1500);
      });
    }
  }

  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-2xl rounded-2xl bg-indigo-600 px-4 py-2.5 text-sm text-white">
          {msg.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-2xl space-y-2">
        <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 whitespace-pre-wrap text-justify">
          {msg.content}
        </div>
        {msg.code && (
          <div className="rounded-xl border border-slate-200 bg-slate-950 text-xs">
            <div className="flex items-center justify-between border-b border-slate-800 px-3 py-1.5">
              <span className="font-mono text-slate-400">python</span>
              <button
                onClick={copyCode}
                className="text-slate-400 hover:text-slate-200"
              >
                {codeCopied ? "✓ copied" : "copy"}
              </button>
            </div>
            <pre className="overflow-x-auto p-3 text-green-300">{msg.code}</pre>
          </div>
        )}
      </div>
    </div>
  );
}

// ── main component ────────────────────────────────────────────────────────────

export function DataAnalysisPanel() {
  // dataset state
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [activeDatasetId, setActiveDatasetId] = useState<string | null>(null);
  const [activeSheet, setActiveSheet] = useState<string | undefined>(undefined);

  // upload
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Google Sheets
  const [sheetUrl, setSheetUrl] = useState("");
  const [connectingSheet, setConnectingSheet] = useState(false);
  const [sheetError, setSheetError] = useState<string | null>(null);

  // conversation
  const [messages, setMessages] = useState<DataMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [querying, setQuerying] = useState(false);
  const [queryError, setQueryError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // datasets loaded flag
  const [datasetsLoaded, setDatasetsLoaded] = useState(false);

  // ── load existing datasets on mount ──────────────────────────────────────

  const loadDatasets = useCallback(async () => {
    try {
      const list = await listDatasets();
      setDatasets(list);
      if (list.length > 0 && !activeDatasetId) {
        setActiveDatasetId(list[0].dataset_id);
        setActiveSheet(list[0].sheets[0]);
      }
    } catch {
      /* non-fatal */
    }
    setDatasetsLoaded(true);
  }, [activeDatasetId]);

  if (!datasetsLoaded) {
    void loadDatasets();
  }

  // ── file upload ───────────────────────────────────────────────────────────

  async function handleFileSelect(file: File) {
    setUploadError(null);
    setUploading(true);
    setUploadProgress(0);
    try {
      const result: DataUploadResponse = await uploadDataset(file, setUploadProgress);
      const newDataset: Dataset = {
        dataset_id: result.dataset_id,
        filename: result.filename,
        rows: result.rows,
        columns: result.columns,
        sheets: result.sheets,
        created_at: new Date().toISOString(),
      };
      setDatasets((prev) => [newDataset, ...prev]);
      setActiveDatasetId(result.dataset_id);
      setActiveSheet(result.sheets[0]);
      setMessages([]);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: { message?: string } } } })
          ?.response?.data?.detail?.message ?? "Upload failed.";
      setUploadError(msg);
    } finally {
      setUploading(false);
      setUploadProgress(0);
    }
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) void handleFileSelect(file);
  }

  // ── Google Sheet connection ───────────────────────────────────────────────

  async function handleConnectSheet() {
    if (!sheetUrl.trim()) return;
    setSheetError(null);
    setConnectingSheet(true);
    try {
      const result = await connectGoogleSheet(sheetUrl.trim());
      const newDataset: Dataset = {
        dataset_id: result.dataset_id,
        filename: result.sheet_title,
        rows: result.rows,
        columns: result.columns,
        sheets: result.sheets,
        created_at: new Date().toISOString(),
        source_url: sheetUrl.trim(),
      };
      setDatasets((prev) => [newDataset, ...prev]);
      setActiveDatasetId(result.dataset_id);
      setActiveSheet(result.sheets[0]);
      setSheetUrl("");
      setMessages([]);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: { message?: string } } } })
          ?.response?.data?.detail?.message ?? "Failed to connect Google Sheet.";
      setSheetError(msg);
    } finally {
      setConnectingSheet(false);
    }
  }

  // ── query ──────────────────────────────────────────────────────────────────

  async function handleAsk() {
    if (!question.trim() || !activeDatasetId || querying) return;

    const q = question.trim();
    setQuestion("");
    setQueryError(null);

    const userMsg: DataMessage = { id: shortId(), role: "user", content: q };
    setMessages((prev) => [...prev, userMsg]);

    // build minimal history for follow-up awareness
    const history = messages.slice(-6).map((m) => ({
      role: m.role === "user" ? "human" : "ai",
      content: m.content,
    }));

    setQuerying(true);
    try {
      const result = await queryDataset(activeDatasetId, q, history, activeSheet);
      const assistantMsg: DataMessage = {
        id: shortId(),
        role: "assistant",
        content: result.answer || "(No answer returned)",
        code: result.code || undefined,
      };
      setMessages((prev) => [...prev, assistantMsg]);
      setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: { message?: string } } } })
          ?.response?.data?.detail?.message ?? "Query failed.";
      setQueryError(msg);
      setMessages((prev) => prev.slice(0, -1)); // remove optimistic user msg on error
    } finally {
      setQuerying(false);
    }
  }

  // ── delete dataset ────────────────────────────────────────────────────────

  async function handleDeleteDataset(datasetId: string) {
    try {
      await deleteDataset(datasetId);
    } catch {
      /* ignore – remove from UI anyway */
    }
    setDatasets((prev) => prev.filter((d) => d.dataset_id !== datasetId));
    if (activeDatasetId === datasetId) {
      const remaining = datasets.filter((d) => d.dataset_id !== datasetId);
      setActiveDatasetId(remaining[0]?.dataset_id ?? null);
      setActiveSheet(remaining[0]?.sheets[0]);
      setMessages([]);
    }
  }

  // ── active dataset info ────────────────────────────────────────────────────

  const activeDataset = datasets.find((d) => d.dataset_id === activeDatasetId);

  // ── render ─────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-full overflow-hidden">
      {/* ── left sidebar ──────────────────────────────────────────────────── */}
      <aside className="flex w-72 shrink-0 flex-col border-r border-slate-200 bg-white p-4 gap-4 overflow-y-auto">
        <h2 className="text-sm font-semibold text-slate-700">📊 Data Analysis</h2>

        {/* Upload area */}
        <div>
          <p className="mb-1.5 text-xs font-medium text-slate-500 uppercase tracking-wide">
            Upload File
          </p>
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 py-5 text-center hover:border-indigo-400 hover:bg-indigo-50 transition-colors"
          >
            <span className="text-2xl">📂</span>
            <p className="mt-1 text-xs text-slate-500">
              Drop CSV / XLSX here
              <br />
              or <span className="text-indigo-600 underline">browse</span>
            </p>
            {uploading && (
              <div className="mt-2 w-full px-4">
                <div className="h-1 w-full overflow-hidden rounded-full bg-slate-200">
                  <div
                    className="h-1 rounded-full bg-indigo-500 transition-all"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
                <p className="mt-1 text-xs text-slate-400">{uploadProgress}%</p>
              </div>
            )}
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.xlsx,.xls"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void handleFileSelect(f);
              e.target.value = "";
            }}
          />
          {uploadError && (
            <p className="mt-1 text-xs text-red-500">{uploadError}</p>
          )}
        </div>

        {/* Google Sheets */}
        <div>
          <p className="mb-1.5 text-xs font-medium text-slate-500 uppercase tracking-wide">
            Google Sheet
          </p>
          <input
            type="url"
            value={sheetUrl}
            onChange={(e) => setSheetUrl(e.target.value)}
            placeholder="https://docs.google.com/spreadsheets/d/..."
            className="w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
          />
          <button
            onClick={() => void handleConnectSheet()}
            disabled={connectingSheet || !sheetUrl.trim()}
            className="mt-1.5 w-full rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {connectingSheet ? "Connecting…" : "Connect Sheet"}
          </button>
          {sheetError && (
            <p className="mt-1 text-xs text-red-500">{sheetError}</p>
          )}
        </div>

        {/* Dataset list */}
        {datasets.length > 0 && (
          <div>
            <p className="mb-1.5 text-xs font-medium text-slate-500 uppercase tracking-wide">
              Datasets ({datasets.length})
            </p>
            <div className="space-y-1.5">
              {datasets.map((ds) => (
                <DatasetBadge
                  key={ds.dataset_id}
                  dataset={ds}
                  active={ds.dataset_id === activeDatasetId}
                  onSelect={() => {
                    setActiveDatasetId(ds.dataset_id);
                    setActiveSheet(ds.sheets[0]);
                    setMessages([]);
                  }}
                  onDelete={() => void handleDeleteDataset(ds.dataset_id)}
                />
              ))}
            </div>
          </div>
        )}
      </aside>

      {/* ── main area ──────────────────────────────────────────────────────── */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Dataset header */}
        {activeDataset ? (
          <div className="border-b border-slate-200 bg-white px-5 py-3 flex items-center gap-3 flex-wrap">
            <div>
              <p className="text-sm font-semibold text-slate-800">
                {activeDataset.filename}
              </p>
              <p className="text-xs text-slate-400">
                {fmtRows(activeDataset.rows)} rows · {activeDataset.columns} columns
              </p>
            </div>
            {activeDataset.sheets.length > 1 && (
              <select
                value={activeSheet}
                onChange={(e) => {
                  setActiveSheet(e.target.value);
                  setMessages([]);
                }}
                className="ml-auto rounded-lg border border-slate-300 px-2 py-1 text-xs outline-none focus:border-indigo-400"
              >
                {activeDataset.sheets.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            )}
          </div>
        ) : (
          <div className="border-b border-slate-200 bg-white px-5 py-3">
            <p className="text-sm text-slate-400">
              Upload a CSV / XLSX or connect a Google Sheet to get started.
            </p>
          </div>
        )}

        {/* Conversation */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {messages.length === 0 && activeDataset && (
            <div className="flex justify-center pt-8">
              <div className="max-w-md rounded-2xl border border-slate-200 bg-white p-6 text-center shadow-sm">
                <p className="text-2xl">🤖</p>
                <p className="mt-2 text-sm font-medium text-slate-700">
                  Ready to analyse <strong>{activeDataset.filename}</strong>
                </p>
                <p className="mt-1 text-xs text-slate-400">
                  Ask any question about your data — totals, trends, filters, summaries…
                </p>
                <div className="mt-4 grid grid-cols-1 gap-1.5 text-left">
                  {[
                    "What are the column names?",
                    "Show me the first 5 rows",
                    "What is the total of the first numeric column?",
                    "Which row has the highest value?",
                  ].map((hint) => (
                    <button
                      key={hint}
                      onClick={() => setQuestion(hint)}
                      className="rounded-lg border border-slate-200 px-3 py-2 text-left text-xs text-slate-600 hover:bg-slate-50"
                    >
                      {hint}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {messages.map((msg) => (
            <MessageBubble key={msg.id} msg={msg} />
          ))}

          {querying && (
            <div className="flex justify-start">
              <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-400 italic">
                Analysing…
              </div>
            </div>
          )}

          {queryError && (
            <p className="text-xs text-red-500 text-center">{queryError}</p>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="border-t border-slate-200 bg-white px-4 py-3">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void handleAsk();
            }}
            className="flex gap-2"
          >
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              disabled={!activeDatasetId || querying}
              placeholder={
                activeDatasetId
                  ? "Ask a question about your data…"
                  : "Upload a dataset first"
              }
              className="flex-1 rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50 disabled:text-slate-400"
            />
            <button
              type="submit"
              disabled={!activeDatasetId || !question.trim() || querying}
              className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              Ask
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
