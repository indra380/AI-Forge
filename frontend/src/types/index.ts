export type ChatRole = "user" | "assistant";

export interface ChatMessage {
	id: string;
	role: ChatRole;
	content: string;
	createdAt?: string;
}

export interface ChatRequest {
	message: string;
	session_id?: string | null;
	attachment_ids?: string[];
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

// ── File attachments ──────────────────────────────────────────────────────────

export interface UploadedFile {
	fileId: string;
	filename: string;
	contentType: string;
	size: number;
	isIndexed: boolean;
	fileUrl?: string;
	attachmentType?: "image" | "video" | "document" | "code" | "table" | "formula" | "file";
}

export type PendingFileStatus = "uploading" | "indexed" | "error";

export interface PendingFile {
	/** Local id used only in the UI list */
	id: string;
	file: File;
	status: PendingFileStatus;
	progress: number;
	previewUrl?: string;
	uploaded?: UploadedFile;
	error?: string;
}

// Backward-compatible aliases used by existing optional panels/components.
export type PendingAttachment = PendingFile;

export type ImageStyle = "realistic" | "anime" | "digital-art" | "cinematic";
export type ImageSize = "1024x1024" | "1024x1536" | "1536x1024";

export interface ImageGenerateRequest {
	prompt: string;
	style: ImageStyle;
	size: ImageSize;
	imageCount: number;
	threadId?: string;
	sessionId?: string;
}

export interface GeneratedImageItem {
	imageId: string;
	imageUrl: string;
	prompt: string;
	style: ImageStyle;
	size: ImageSize;
	createdAt?: string;
}

export interface RagDocument {
	documentId: string;
	filename: string;
	status: string;
}

export interface RagCitation {
	filename: string;
	page: number;
	snippet?: string;
}

export interface RagResponse {
	response: string;
	citations: RagCitation[];
}

