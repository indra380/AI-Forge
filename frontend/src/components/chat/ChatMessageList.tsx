import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import type { ChatMessage } from "../../types";

interface ChatMessageListProps {
  messages: ChatMessage[];
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
            <div className="text-justify text-sm leading-7">
              <ReactMarkdown
                remarkPlugins={[remarkGfm, remarkMath]}
                rehypePlugins={[rehypeHighlight, rehypeKatex]}
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
