import React, { useCallback, useRef, useState } from "react";
import { askResearchFollowup, getResearchMessages, startResearch } from "../../lib/api";
import type { DigestResult, ResearchMessageItem } from "../../types";

const cleanDisplayText = (value: string | undefined): string => {
  if (!value) return "";
  return value
    .replace(/^##\s+/gm, "")
    .replace(/\*\*/g, "")
    .replace(/^\s*[-*]\s+/gm, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
};

const renderFormattedText = (value: string | undefined): React.ReactNode => {
  const text = cleanDisplayText(value);
  if (!text) return null;

  const blocks = text.split(/\n\s*\n/).filter(Boolean);

  return blocks.map((block, idx) => {
    const normalized = block.trim();
    const labelMatch = normalized.match(/^([A-Z][A-Za-z0-9/&,\-\s]{2,80}:)\s*(.*)$/);

    if (labelMatch) {
      return (
        <p key={`blk-${idx}`}>
          <strong className="font-semibold text-slate-900 dark:text-slate-100">{labelMatch[1]}</strong>{" "}
          {labelMatch[2]}
        </p>
      );
    }

    return <p key={`blk-${idx}`}>{normalized}</p>;
  });
};

const SectionCard: React.FC<{
  title: string;
  children: React.ReactNode;
}> = ({ title, children }) => (
  <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
    <h3 className="text-sm font-semibold tracking-wide text-slate-700 dark:text-slate-200 uppercase">{title}</h3>
    <div className="mt-3 text-sm leading-7 text-slate-700 dark:text-slate-300 whitespace-pre-wrap wrap-break-word text-justify">
      {children}
    </div>
  </section>
);

export const ResearchDigestPanel: React.FC = () => {
  const [query, setQuery] = useState("");
  const [followup, setFollowup] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isAsking, setIsAsking] = useState(false);
  const [status, setStatus] = useState("");
  const [digest, setDigest] = useState<DigestResult | null>(null);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ResearchMessageItem[]>([]);
  const resultsRef = useRef<HTMLDivElement>(null);

  const loadMessages = useCallback(async (nextThreadId: string) => {
    const rows = await getResearchMessages(nextThreadId);
    setMessages(rows);
  }, []);

  const handleStartResearch = useCallback(async () => {
    if (!query.trim()) return;

    setIsLoading(true);
    setStatus("Starting research...");
    setDigest(null);
    setThreadId(null);
    setMessages([]);

    try {
      const response = await startResearch({ query });

      if (!response.body) {
        throw new Error("No response body");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");

        // Process complete lines, keep incomplete line in buffer
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = line.slice(6);
            try {
              const parsed = JSON.parse(data);

              if (parsed.type) {
                // It's a stream event
                setStatus(parsed.message);
                if (parsed.type === "papers" && Array.isArray(parsed.papers)) {
                  setDigest({
                    thread_id: parsed.thread_id || "",
                    query: parsed.query || query,
                    summary: "",
                    summary_display: "",
                    papers: parsed.papers,
                    trends: [],
                    keywords: [],
                    synthesis: "",
                    total_papers_analyzed: parsed.papers.length,
                  });
                  if (parsed.thread_id) {
                    setThreadId(parsed.thread_id);
                  }
                }
              } else if (parsed.query) {
                // It's the final result
                const result = parsed as DigestResult;
                setDigest(result);
                setThreadId(result.thread_id);
                setStatus("✓ Research complete!");
                void loadMessages(result.thread_id);
              }
            } catch (e) {
              console.error("Error parsing event:", e);
            }
          }
        }
      }

      setIsLoading(false);
    } catch (error) {
      setStatus(`Error: ${error instanceof Error ? error.message : "Unknown error"}`);
      setIsLoading(false);
    }
  }, [query, loadMessages]);

  const handleAskFollowup = useCallback(async () => {
    if (!threadId || !followup.trim()) {
      return;
    }

    setIsAsking(true);
    try {
      await askResearchFollowup(threadId, { question: followup });
      setFollowup("");
      await loadMessages(threadId);
    } catch (error) {
      setStatus(`Error: ${error instanceof Error ? error.message : "Unknown error"}`);
    } finally {
      setIsAsking(false);
    }
  }, [threadId, followup, loadMessages]);

  const summaryForDisplay = cleanDisplayText(digest?.summary_display || digest?.summary);

  return (
    <div className="flex h-full flex-col bg-slate-50 dark:bg-slate-950">
      {/* Header */}
      <div className="border-b border-slate-200 bg-white/80 p-5 backdrop-blur dark:border-slate-800 dark:bg-slate-950/80">
        <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Research Digest</h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          Structured research briefs from ArXiv with clear findings and next questions.
        </p>

        {/* Research Query Input */}
        <div className="mt-4 space-y-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
              Research Topic
            </label>
            <input
              type="text"
              placeholder="e.g., Large language models, Neural networks, Machine learning"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyPress={(e) => e.key === "Enter" && handleStartResearch()}
              disabled={isLoading}
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 shadow-sm transition focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-white dark:focus:border-blue-500 dark:focus:ring-blue-950"
            />
          </div>

          <button
            onClick={handleStartResearch}
            disabled={isLoading || !query.trim()}
            className="w-full rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400 dark:bg-blue-600 dark:hover:bg-blue-500"
          >
            {isLoading ? "Researching..." : "Start Research"}
          </button>
        </div>

        {/* Status Line */}
        {status && (
          <div className="mt-3 rounded-md bg-slate-100 px-3 py-2 text-xs font-medium text-slate-700 dark:bg-slate-900 dark:text-slate-300">
            {status}
          </div>
        )}
      </div>

      {/* Results */}
      <div ref={resultsRef} className="flex-1 space-y-4 overflow-y-auto p-5">
        {digest ? (
          <div className="space-y-5">
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
              <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-xs text-slate-600 shadow-sm dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300">
                <span className="font-semibold text-slate-900 dark:text-slate-100">Query:</span> {digest.query}
              </div>
              <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-xs text-slate-600 shadow-sm dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300">
                <span className="font-semibold text-slate-900 dark:text-slate-100">Papers analyzed:</span> {digest.total_papers_analyzed}
              </div>
            </div>

            <SectionCard title="Topic Summary">
              {summaryForDisplay ? renderFormattedText(summaryForDisplay) : "No summary available."}
            </SectionCard>

            {digest.key_findings && (
              <SectionCard title="Key Findings">
                {renderFormattedText(digest.key_findings)}
              </SectionCard>
            )}

            {digest.consensus_view && (
              <SectionCard title="Consensus View">
                {renderFormattedText(digest.consensus_view)}
              </SectionCard>
            )}

            {digest.open_questions && (
              <SectionCard title="Open Questions">
                {renderFormattedText(digest.open_questions)}
              </SectionCard>
            )}

            {digest.confidence && (
              <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
                <h3 className="text-sm font-semibold tracking-wide text-slate-700 dark:text-slate-200 uppercase">Confidence Assessment</h3>
                <div className="mt-3 grid grid-cols-1 gap-2 text-sm md:grid-cols-2">
                  <div className="rounded-md bg-slate-50 px-3 py-2 dark:bg-slate-900">
                    <span className="font-medium">Level:</span> {digest.confidence.level || "N/A"}
                  </div>
                  <div className="rounded-md bg-slate-50 px-3 py-2 dark:bg-slate-900">
                    <span className="font-medium">Maturity:</span> {digest.confidence.maturity || "N/A"}
                  </div>
                  <div className="rounded-md bg-slate-50 px-3 py-2 dark:bg-slate-900">
                    <span className="font-medium">Sample Size:</span> {digest.confidence.sample_size ?? "N/A"}
                  </div>
                  <div className="rounded-md bg-slate-50 px-3 py-2 dark:bg-slate-900">
                    <span className="font-medium">Recent Activity:</span> {digest.confidence.recent_activity ?? "N/A"}
                  </div>
                </div>
                {digest.confidence.description && (
                  <p className="mt-3 text-sm leading-7 text-slate-700 dark:text-slate-300 text-justify">
                    {digest.confidence.description}
                  </p>
                )}
              </section>
            )}

            {/* Trends */}
            {digest.trends && digest.trends.length > 0 && (
              <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
                <h3 className="text-sm font-semibold tracking-wide text-slate-700 dark:text-slate-200 uppercase">
                  Trends
                </h3>
                <div className="flex flex-wrap gap-2">
                  {digest.trends.map((trend: string, i: number) => (
                    <span
                      key={i}
                      className="rounded-full border border-slate-200 bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
                    >
                      {trend}
                    </span>
                  ))}
                </div>
              </section>
            )}

            {digest.keywords && digest.keywords.length > 0 && (
              <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
                <h3 className="text-sm font-semibold tracking-wide text-slate-700 dark:text-slate-200 uppercase">
                  Keywords
                </h3>
                <div className="mt-3 flex flex-wrap gap-2">
                  {digest.keywords.map((keyword: string, i: number) => (
                    <span
                      key={i}
                      className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-800 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-200"
                    >
                      {keyword}
                    </span>
                  ))}
                </div>
              </section>
            )}

            {/* Synthesis */}
            <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
              <h3 className="text-sm font-semibold tracking-wide text-slate-700 dark:text-slate-200 uppercase">
                Synthesis
              </h3>
              <div className="mt-3 text-sm leading-7 text-slate-700 dark:text-slate-300 text-justify">
                {digest.synthesis}
              </div>
            </section>

            {/* Key Papers */}
            {digest.papers && digest.papers.length > 0 && (
              <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
                <h3 className="text-sm font-semibold tracking-wide text-slate-700 dark:text-slate-200 uppercase">
                  Key Papers
                </h3>
                <div className="mt-3 space-y-3">
                  {digest.papers.map((paper: typeof digest.papers[0]) => (
                    <div
                      key={paper.arxiv_id}
                      className="rounded-lg border border-slate-200 p-3 transition hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-900"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <a
                            href={paper.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="block truncate font-medium text-blue-700 hover:underline dark:text-blue-400"
                            title={paper.title}
                          >
                            {paper.title}
                          </a>
                          <p className="text-xs text-slate-600 dark:text-slate-400 mt-1">
                            {paper.authors.slice(0, 3).join(", ")}
                            {paper.authors.length > 3 && " et al."}
                          </p>
                          <p className="text-xs text-slate-500 dark:text-slate-500 mt-1">
                            {new Date(paper.published).toLocaleDateString()} • {paper.arxiv_id}
                          </p>
                          <p className="mt-2 line-clamp-2 text-xs text-slate-700 dark:text-slate-300">
                            {paper.summary}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Chat-style follow-up */}
            <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
              <h3 className="text-sm font-semibold tracking-wide text-slate-700 dark:text-slate-200 uppercase">
                Follow-up Questions
              </h3>

              <div className="mt-3 space-y-3">
                <div className="max-h-72 overflow-y-auto rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-950">
                  {messages.length === 0 ? (
                    <p className="text-sm text-slate-500 dark:text-slate-400">
                      Your research conversation will appear here.
                    </p>
                  ) : (
                    <div className="space-y-2">
                      {messages.map((m) => (
                        <div
                          key={m.id}
                          className={`rounded-lg px-3 py-2 text-sm whitespace-pre-wrap text-justify ${
                            m.role === "user"
                              ? "bg-blue-50 text-blue-900 dark:bg-blue-950/40 dark:text-blue-100"
                              : "bg-slate-100 text-slate-900 dark:bg-slate-800 dark:text-slate-100"
                          }`}
                        >
                          <div className="mb-1 text-[11px] uppercase tracking-wide opacity-70">
                            {m.role}
                          </div>
                          {m.content}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="flex gap-2">
                  <input
                    type="text"
                    value={followup}
                    onChange={(e) => setFollowup(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        void handleAskFollowup();
                      }
                    }}
                    disabled={!threadId || isAsking}
                    placeholder="Ask a follow-up question about this research..."
                    className="flex-1 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-900 dark:text-white"
                  />
                  <button
                    type="button"
                    onClick={() => void handleAskFollowup()}
                    disabled={!threadId || isAsking || !followup.trim()}
                    className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-blue-600 dark:hover:bg-blue-500"
                  >
                    {isAsking ? "Asking..." : "Ask"}
                  </button>
                </div>
              </div>
            </section>
          </div>
        ) : !isLoading && !status ? (
          <div className="flex h-full items-center justify-center text-slate-500 dark:text-slate-400">
            <div className="text-center">
              <p className="mb-2 text-lg">Enter a research topic to begin</p>
              <p className="text-sm">Examples: Large language models, Transformer architectures, Deep reinforcement learning</p>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default ResearchDigestPanel;
