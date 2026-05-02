import { useMutation } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";

import { streamChat } from "../lib/api";
import type { ChatMessage, ChatStreamEvent } from "../types";

function makeId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export function useChat(onThreadRenamed?: (title: string) => void) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);

  // Ref so the mutationFn always reads the latest callback without stale closure
  const onThreadRenamedRef = useRef(onThreadRenamed);
  onThreadRenamedRef.current = onThreadRenamed;

  const mutation = useMutation({
    mutationFn: async ({ message, threadId }: { message: string; threadId: string }) => {
      const userMessage: ChatMessage = { id: makeId(), role: "user", content: message };
      const assistantMessageId = makeId();
      const assistantMessage: ChatMessage = { id: assistantMessageId, role: "assistant", content: "" };

      setMessages((prev) => [...prev, userMessage, assistantMessage]);

      await streamChat(threadId, { message }, (event: ChatStreamEvent) => {
        if (event.type === "token" && event.content) {
          setMessages((prev) =>
            prev.map((entry) =>
              entry.id === assistantMessageId
                ? { ...entry, content: entry.content + event.content }
                : entry
            )
          );
        }
        if (event.type === "thread_renamed" && event.content) {
          onThreadRenamedRef.current?.(event.content);
        }
        if (event.type === "error") {
          const errorMessage = event.message ?? "Unexpected chat error";
          setMessages((prev) =>
            prev.map((entry) =>
              entry.id === assistantMessageId
                ? { ...entry, content: `Error: ${errorMessage}` }
                : entry
            )
          );
        }
      });
    },
  });

  const hasMessages = useMemo(() => messages.length > 0, [messages.length]);

  // Accepts an explicit threadId so callers that just set state can bypass the stale closure
  function sendMessageToThread(message: string, threadId: string) {
    return mutation.mutateAsync({ message, threadId });
  }

  function sendMessage(message: string) {
    if (!activeThreadId) return Promise.resolve();
    return mutation.mutateAsync({ message, threadId: activeThreadId });
  }

  return {
    messages,
    hasMessages,
    setMessages,
    activeThreadId,
    setActiveThreadId,
    sendMessage,
    sendMessageToThread,
    isStreaming: mutation.isPending,
  };
}

