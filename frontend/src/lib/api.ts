// All API calls go through this module — never call fetch/axios directly in components.
import axios from "axios";
import { z } from "zod";

import type {
  AuthUser,
  ChatMessage,
  ChatRequest,
  ChatStreamEvent,
  ChatThread,
  LoginRequest,
  RegisterRequest,
} from "../types";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000",
  withCredentials: true,
  headers: {
    "Content-Type": "application/json",
  },
});

const chatStreamEventSchema = z.object({
  type: z.enum(["token", "done", "error", "thread_renamed"]),
  content: z.string().optional(),
  message: z.string().optional(),
});

const authUserSchema = z.object({
  id: z.string(),
  email: z.string(),
  google_id: z.string().nullable().optional(),
});

const chatHistoryItemSchema = z.object({
  id: z.string(),
  role: z.enum(["user", "assistant"]),
  content: z.string(),
  created_at: z.string(),
});

const threadSchema = z.object({
  id: z.string(),
  title: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
});

function getBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
}

export async function register(payload: RegisterRequest): Promise<AuthUser> {
  const response = await api.post("/api/auth/register", payload);
  return authUserSchema.parse(response.data);
}

export async function login(payload: LoginRequest): Promise<AuthUser> {
  const response = await api.post("/api/auth/login", payload);
  return authUserSchema.parse(response.data);
}

export async function me(): Promise<AuthUser> {
  const response = await api.get("/api/auth/me");
  return authUserSchema.parse(response.data);
}

export async function logout(): Promise<void> {
  await api.post("/api/auth/logout");
}

export function getGoogleLoginUrl(): string {
  return `${getBaseUrl()}/api/auth/google`;
}

// ── Threads ───────────────────────────────────────────────────────────────────

export async function getThreads(): Promise<ChatThread[]> {
  const response = await api.get("/api/chat/threads");
  return z.array(threadSchema).parse(response.data);
}

export async function createThread(title = "New Chat"): Promise<ChatThread> {
  const response = await api.post("/api/chat/threads", { title });
  return threadSchema.parse(response.data);
}

export async function renameThread(threadId: string, title: string): Promise<ChatThread> {
  const response = await api.patch(`/api/chat/threads/${threadId}`, { title });
  return threadSchema.parse(response.data);
}

export async function deleteThread(threadId: string): Promise<void> {
  await api.delete(`/api/chat/threads/${threadId}`);
}

// ── Messages ──────────────────────────────────────────────────────────────────

export async function getThreadMessages(threadId: string): Promise<ChatMessage[]> {
  const response = await api.get(`/api/chat/threads/${threadId}/messages`);
  const parsed = z.array(chatHistoryItemSchema).parse(response.data);
  return parsed.map((item) => ({
    id: item.id,
    role: item.role as "user" | "assistant",
    content: item.content,
    createdAt: item.created_at,
  }));
}

export async function streamChat(
  threadId: string,
  payload: ChatRequest,
  onEvent: (event: ChatStreamEvent) => void
): Promise<void> {
  const response = await fetch(`${getBaseUrl()}/api/chat/threads/${threadId}/stream`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok || !response.body) {
    throw new Error(`Chat stream failed with status ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";

    for (const chunk of chunks) {
      const line = chunk.split("\n").find((segment) => segment.startsWith("data: "));
      if (!line) continue;
      const raw = line.slice(6);
      const event = chatStreamEventSchema.parse(JSON.parse(raw));
      onEvent(event);
    }
  }
}

export default api;

