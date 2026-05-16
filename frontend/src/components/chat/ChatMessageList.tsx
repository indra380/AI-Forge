import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { useState } from "react";

import type { ChatMessage } from "../../types";
import { ValidationReport } from "./ValidationReport";

interface ChatMessageListProps {
  messages: ChatMessage[];
}

// Custom code block renderer that detects special languages
function CustomCodeBlock({
  className,
  children,
  inline,
}: {
  className?: string;
  children: React.ReactNode;
  inline?: boolean;
}) {
  const lang = /language-(\w+)/.exec(className ?? "")?.[1];
  const raw = String(children).trim();
  const [copied, setCopied] = useState(false);

  if (lang === "validation") {
    try {
      const report = JSON.parse(raw);
      return <ValidationReport {...report} />;
    } catch {
      // fall through
    }
  }

  if (inline) {
    return (
      <code className="rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[0.85em] text-slate-800">
        {children}
      </code>
    );
  }

  const languageLabel = lang ? lang.toUpperCase() : "TEXT";

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(raw);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="my-3 overflow-hidden rounded-xl border border-slate-200 bg-slate-950 shadow-inner">
      <div className="flex items-center justify-between border-b border-slate-800 px-3 py-1.5">
        <span className="text-[11px] font-semibold tracking-wide text-slate-300">{languageLabel}</span>
        <button
          type="button"
          onClick={handleCopy}
          className="rounded-md border border-slate-700 px-2 py-0.5 text-[11px] font-medium text-slate-300 hover:bg-slate-800"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto p-3 text-slate-100">
        <code className={className}>{children}</code>
      </pre>
    </div>
  );
}

export function ChatMessageList({ messages }: ChatMessageListProps) {
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-3 overflow-y-auto px-4 py-6">
      {messages.map((message) => {
        const isUser = message.role === "user";

        return (
          <div
            key={message.id}
            className={`max-w-3xl rounded-2xl p-4 shadow-sm ${
              isUser
                ? "ml-auto bg-slate-900 text-slate-100"
                : "mr-auto border border-slate-200 bg-white text-slate-900"
            }`}
          >
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              {isUser ? "You" : "Assistant"}
            </p>
            <div className={`chat-markdown text-sm leading-7 ${isUser ? "chat-markdown-user" : "chat-markdown-assistant"}`}>
              <ReactMarkdown
                remarkPlugins={[remarkGfm, remarkMath]}
                rehypePlugins={[rehypeHighlight, rehypeKatex]}
                components={{
                  code: CustomCodeBlock as React.ComponentType<React.HTMLAttributes<HTMLElement>>,
                  table: ({ children }) => (
                    <div className="my-3 overflow-x-auto rounded-xl border border-slate-200 bg-white">
                      <table className="min-w-full border-collapse text-left text-sm">{children}</table>
                    </div>
                  ),
                  thead: ({ children }) => <thead className="bg-slate-50">{children}</thead>,
                  th: ({ children }) => (
                    <th className="border-b border-slate-200 px-3 py-2 font-semibold text-slate-700">{children}</th>
                  ),
                  td: ({ children }) => <td className="border-b border-slate-100 px-3 py-2 align-top">{children}</td>,
                  a: ({ href, children }) => (
                    <a href={href} target="_blank" rel="noreferrer" className="font-medium text-blue-600 underline">
                      {children}
                    </a>
                  ),
                }}
              >
                {message.content || "..."}
              </ReactMarkdown>
            </div>
          </div>
        );
      })}
    </div>
  );
}
