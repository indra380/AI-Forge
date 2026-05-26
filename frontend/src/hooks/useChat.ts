import { useMutation } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";

import { streamChat } from "../lib/api";
import type { ChatMessage, ChatStreamEvent } from "../types";

const SESSION_STORAGE_KEY = "amzur.chat.sessions.v1";

function makeId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function newSessionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return makeId();
}

function loadSessions(): Record<string, string> {
  try {
    const raw = localStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object") return {};
    const result: Record<string, string> = {};
    for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof v === "string") result[k] = v;
    }
    return result;
  } catch {
    return {};
  }
}

function saveSessions(map: Record<string, string>) {
  localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(map));
}

export function useChat(onThreadRenamed?: (title: string) => void) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  const onThreadRenamedRef = useRef(onThreadRenamed);
  onThreadRenamedRef.current = onThreadRenamed;

  /** Get or create a stable session UUID for a thread. */
  function getOrCreateSession(threadId: string): string {
    const map = loadSessions();
    if (map[threadId]) return map[threadId];
    const sid = newSessionId();
    map[threadId] = sid;
    saveSessions(map);
    return sid;
  }

  /** Called when selecting or creating a thread — sets state + returns session. */
  function activateThread(threadId: string): string {
    const sid = getOrCreateSession(threadId);
    setActiveThreadId(threadId);
    setActiveSessionId(sid);
    return sid;
  }

  /** Ensure a session exists for the composer even before a thread is created. */
  function ensureComposerSession(): string {
    if (activeSessionId) return activeSessionId;
    const sid = newSessionId();
    setActiveSessionId(sid);
    return sid;
  }

  const mutation = useMutation({
    mutationFn: async ({
      message,
      threadId,
      sessionId,
      attachmentIds,
    }: {
      message: string;
      threadId: string;
      sessionId: string;
      attachmentIds?: string[];
    }) => {
      const userMessage: ChatMessage = { id: makeId(), role: "user", content: message };
      const assistantMessageId = makeId();
      const assistantMessage: ChatMessage = { id: assistantMessageId, role: "assistant", content: "" };

      setMessages((prev) => [...prev, userMessage, assistantMessage]);

      await streamChat(
        threadId,
        { message, session_id: sessionId, attachment_ids: attachmentIds ?? [] },
        (event: ChatStreamEvent) => {
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
      }
      );
    },
  });

  const hasMessages = useMemo(() => messages.length > 0, [messages.length]);

  function sendMessageToThread(
    message: string,
    threadId: string,
    sessionId: string,
    attachmentIds: string[] = []
  ) {
    return mutation.mutateAsync({ message, threadId, sessionId, attachmentIds });
  }

  function sendMessage(message: string, attachmentIds: string[] = []) {
    if (!activeThreadId || !activeSessionId) return Promise.resolve();
    return mutation.mutateAsync({
      message,
      threadId: activeThreadId,
      sessionId: activeSessionId,
      attachmentIds,
    });
  }

  return {
    messages,
    hasMessages,
    setMessages,
    activeThreadId,
    setActiveThreadId,
    activeSessionId,
    setActiveSessionId,
    activateThread,
    ensureComposerSession,
    sendMessage,
    sendMessageToThread,
    isStreaming: mutation.isPending,
  };
}

