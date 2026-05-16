// All API calls go through this module — never call fetch/axios directly in components.
import axios from "axios";
import { z } from "zod";

import type {
  AuthUser,
  ChatMessage,
  ChatRequest,
  ChatStreamEvent,
  ChatThread,
  DbConnection,
  DbConnectionCreate,
  GeneratedImageItem,
  ImageGenerateRequest,
  ImageRule,
  LoginRequest,
  RagResponse,
  RagDocument,
  RegisterRequest,
  RuleItem,
  UploadedFile,
  Dataset,
  DataUploadResponse,
  DataGoogleSheetResponse,
  DataQueryResponse,
  ResearchQueryRequest,
  ResearchFollowupRequest,
  ResearchFollowupResponse,
  ResearchMessageItem,
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

const uploadResponseSchema = z.object({
  file_id: z.string(),
  filename: z.string(),
  content_type: z.string(),
  size: z.number(),
  is_indexed: z.boolean(),
  file_url: z.string().nullable().optional(),
  attachment_type: z.string().nullable().optional(),
});

const generatedImageSchema = z.object({
  image_id: z.string(),
  image_url: z.string(),
  prompt: z.string(),
  style: z.string(),
  size: z.string(),
  created_at: z.string().optional(),
});

const imageGenerateResponseSchema = z.object({
  images: z.array(generatedImageSchema).default([]),
});

const ragUploadResponseSchema = z.object({
  document_id: z.string(),
  filename: z.string(),
  status: z.string(),
});

const ragCitationSchema = z.object({
  filename: z.string(),
  page: z.number(),
  chunk_index: z.number().optional(),
});

const ragChatResponseSchema = z.object({
  response: z.string(),
  citations: z.array(ragCitationSchema).default([]),
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

// ── File upload ───────────────────────────────────────────────────────────────

export async function uploadFile(
  sessionId: string,
  file: File,
  onProgress?: (pct: number) => void,
): Promise<UploadedFile> {
  const form = new FormData();
  form.append("session_id", sessionId);
  form.append("file", file);

  const response = await api.post("/api/chat/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (event) => {
      if (onProgress && event.total) {
        onProgress(Math.round((event.loaded * 100) / event.total));
      }
    },
  });

  const parsed = uploadResponseSchema.parse(response.data);
  return {
    fileId: parsed.file_id,
    filename: parsed.filename,
    contentType: parsed.content_type,
    size: parsed.size,
    isIndexed: parsed.is_indexed,
    fileUrl: parsed.file_url ?? undefined,
    attachmentType:
      (parsed.attachment_type as UploadedFile["attachmentType"] | null | undefined) ?? undefined,
  };
}

export async function deleteUploadedFile(fileId: string, sessionId: string): Promise<void> {
  await api.delete(`/api/chat/upload/${fileId}`, { params: { session_id: sessionId } });
}

// ── Image generation ─────────────────────────────────────────────────────────

export async function generateImages(payload: ImageGenerateRequest): Promise<GeneratedImageItem[]> {
  const response = await api.post("/api/image/generate", {
    prompt: payload.prompt,
    style: payload.style,
    size: payload.size,
    image_count: payload.imageCount,
    thread_id: payload.threadId,
    session_id: payload.sessionId,
  });

  const parsed = imageGenerateResponseSchema.parse(response.data);
  const baseUrl = getBaseUrl();
  return parsed.images.map((image) => ({
    imageId: image.image_id,
    imageUrl:
      image.image_url.startsWith("http")
        ? image.image_url
        : `${baseUrl}${image.image_url.startsWith("/") ? "" : "/"}${image.image_url}`,
    prompt: image.prompt,
    style: image.style as GeneratedImageItem["style"],
    size: image.size as GeneratedImageItem["size"],
    createdAt: image.created_at,
  }));
}

// ── Classic single-document RAG panel ───────────────────────────────────────

export async function ragUploadPdf(sessionId: string, file: File): Promise<RagDocument> {
  const form = new FormData();
  form.append("session_id", sessionId);
  form.append("file", file);

  const response = await api.post("/api/rag/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });

  const parsed = ragUploadResponseSchema.parse(response.data);
  return {
    documentId: parsed.document_id,
    filename: parsed.filename,
    status: parsed.status,
  };
}

export async function ragAsk(
  sessionId: string,
  documentId: string,
  message: string,
): Promise<RagResponse> {
  const response = await api.post("/api/rag/chat", {
    session_id: sessionId,
    document_id: documentId,
    message,
  });

  const parsed = ragChatResponseSchema.parse(response.data);
  return {
    response: parsed.response,
    citations: parsed.citations.map((citation) => ({
      filename: citation.filename,
      page: citation.page,
    })),
  };
}

// ── Streaming chat ────────────────────────────────────────────────────────────

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

// ── Database connections ─────────────────────────────────────────────────────

const dbConnectionSchema = z.object({
  id: z.string(),
  name: z.string(),
  db_type: z.string(),
  host: z.string().nullable().optional(),
  port: z.number().nullable().optional(),
  database: z.string().nullable().optional(),
  username: z.string().nullable().optional(),
  created_at: z.string(),
});

export async function createDbConnection(payload: DbConnectionCreate): Promise<DbConnection> {
  const response = await api.post("/api/agent/db-connections", payload);
  return dbConnectionSchema.parse(response.data) as DbConnection;
}

export async function getDbConnections(): Promise<DbConnection[]> {
  const response = await api.get("/api/agent/db-connections");
  return z.array(dbConnectionSchema).parse(response.data) as DbConnection[];
}

export async function deleteDbConnection(connectionId: string): Promise<void> {
  await api.delete(`/api/agent/db-connections/${connectionId}`);
}

export async function setThreadDbConnection(
  threadId: string,
  connectionId: string
): Promise<void> {
  await api.post(`/api/agent/threads/${threadId}/set-db`, null, {
    params: { connection_id: connectionId },
  });
}

export async function clearThreadDbConnection(threadId: string): Promise<void> {
  await api.delete(`/api/agent/threads/${threadId}/set-db`);
}

export async function getDbSchema(connectionId: string): Promise<string> {
  const response = await api.get(`/api/agent/db-connections/${connectionId}/schema`);
  return (response.data as { schema: string }).schema;
}

// ── Image rules ──────────────────────────────────────────────────────────────

const imageRuleSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().nullable().optional(),
  rules: z.array(z.object({
    field: z.string(),
    operator: z.string(),
    value: z.unknown().optional(),
    type: z.string().optional(),
    label: z.string().optional(),
  })),
  created_at: z.string(),
});

export async function getImageRules(): Promise<ImageRule[]> {
  const response = await api.get("/api/agent/image-rules");
  return z.array(imageRuleSchema).parse(response.data) as ImageRule[];
}

export async function createImageRule(payload: {
  name: string;
  description?: string;
  rules: RuleItem[];
}): Promise<ImageRule> {
  const response = await api.post("/api/agent/image-rules", payload);
  return imageRuleSchema.parse(response.data) as ImageRule;
}

export async function deleteImageRule(ruleId: string): Promise<void> {
  await api.delete(`/api/agent/image-rules/${ruleId}`);
}

// ── Data Analysis ──────────────────────────────────────────────────────────

export async function uploadDataset(
  file: File,
  onProgress?: (pct: number) => void,
): Promise<DataUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const response = await api.post("/api/data/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (event) => {
      if (onProgress && event.total) {
        onProgress(Math.round((event.loaded * 100) / event.total));
      }
    },
  });
  return response.data as DataUploadResponse;
}

export async function connectGoogleSheet(
  google_sheet_url: string,
  worksheet_name?: string,
): Promise<DataGoogleSheetResponse> {
  const response = await api.post("/api/data/google-sheet", {
    google_sheet_url,
    worksheet_name: worksheet_name ?? null,
  });
  return response.data as DataGoogleSheetResponse;
}

export async function queryDataset(
  dataset_id: string,
  question: string,
  history?: Array<{ role: string; content: string }>,
  sheet_name?: string,
): Promise<DataQueryResponse> {
  const response = await api.post("/api/data/query", {
    dataset_id,
    question,
    history: history ?? [],
    sheet_name: sheet_name ?? null,
  });
  return response.data as DataQueryResponse;
}

export async function listDatasets(): Promise<Dataset[]> {
  const response = await api.get("/api/data/datasets");
  return (response.data as { datasets: Dataset[] }).datasets;
}

export async function deleteDataset(dataset_id: string): Promise<void> {
  await api.delete(`/api/data/${dataset_id}`);
}

// ── Research Digest Agent ────────────────────────────────────────────────────

export async function startResearch(
  payload: ResearchQueryRequest
): Promise<Response> {
  // Use fetch to POST and get Response with streaming body
  const response = await fetch(
    `${api.defaults.baseURL}/api/research/digest`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      credentials: "include",
    }
  );

  if (!response.ok) {
    throw new Error(`Research API error: ${response.statusText}`);
  }

  return response;
}

export async function askResearchFollowup(
  threadId: string,
  payload: ResearchFollowupRequest
): Promise<ResearchFollowupResponse> {
  const response = await api.post(`/api/research/threads/${threadId}/ask`, payload);
  return response.data as ResearchFollowupResponse;
}

export async function getResearchMessages(threadId: string): Promise<ResearchMessageItem[]> {
  const response = await api.get(`/api/research/threads/${threadId}/messages`);
  return response.data as ResearchMessageItem[];
}

export default api;

