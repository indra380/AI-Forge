export type ChatRole = "user" | "assistant";

export interface ChatMessage {
	id: string;
	role: ChatRole;
	content: string;
	createdAt?: string;
}

export interface ChatRequest {
	message: string;
}

export interface ChatResponse {
	answer: string;
}

export type ChatStreamEventType = "token" | "done" | "error" | "thread_renamed";

export interface ChatStreamEvent {
	type: ChatStreamEventType;
	content?: string;
	message?: string;
}

export interface LoginRequest {
	email: string;
	password: string;
}

export interface RegisterRequest {
	email: string;
	password: string;
}

export interface AuthUser {
	id: string;
	email: string;
	google_id?: string | null;
}

export interface ChatThread {
	id: string;
	title: string;
	created_at: string;
	updated_at: string;
}

