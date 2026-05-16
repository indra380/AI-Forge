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

// ── Database connections ──────────────────────────────────────────────────────

export interface DbConnection {
	id: string;
	name: string;
	db_type: string;
	host?: string | null;
	port?: number | null;
	database?: string | null;
	username?: string | null;
	created_at: string;
}

export interface DbConnectionCreate {
	name: string;
	db_type: string;
	host?: string;
	port?: number;
	database?: string;
	username?: string;
	password?: string;
	full_url?: string;
}

// ── Data analysis ────────────────────────────────────────────────────────────

export interface Dataset {
  dataset_id: string;
  filename: string;
  rows: number;
  columns: number;
  sheets: string[];
  created_at: string;
  source_url?: string | null;
}

export interface DataUploadResponse {
  dataset_id: string;
  filename: string;
  rows: number;
  columns: number;
  sheets: string[];
}

export interface DataGoogleSheetResponse {
  dataset_id: string;
  sheet_title: string;
  rows: number;
  columns: number;
  sheets: string[];
}

export interface DataQueryResponse {
  answer: string;
  code: string;
  data_summary: string;
  error?: string | null;
}

export interface DataMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  code?: string;
}

// ── Research digest agent ────────────────────────────────────────────────────

export interface ResearchQueryRequest {
  query: string;
  max_papers?: number;
	thread_id?: string;
}

export interface PaperReference {
  arxiv_id: string;
  title: string;
  authors: string[];
  published: string;
  url: string;
  summary: string;
}

export interface ResearchStreamEvent {
  type: "searching" | "analyzing" | "complete" | "error";
  message: string;
  papers_found?: number;
  current_paper?: PaperReference;
}

export interface DigestResult {
	thread_id: string;
  query: string;
  summary: string;
	summary_display?: string;
  papers: PaperReference[];
  trends: string[];
	keywords?: string[];
	key_findings?: string;
	consensus_view?: string;
	open_questions?: string;
	confidence?: {
		level?: string;
		description?: string;
		maturity?: string;
		sample_size?: number;
		recent_activity?: number;
	};
  synthesis: string;
  total_papers_analyzed: number;
}

export interface ResearchFollowupRequest {
	question: string;
}

export interface ResearchFollowupResponse {
	thread_id: string;
	answer: string;
}

export interface ResearchMessageItem {
	id: string;
	role: "user" | "assistant";
	content: string;
	created_at: string;
}

// ── Image rules ──────────────────────────────────────────────────────────────

export interface RuleItem {
	field: string;
	operator: string;
	value?: unknown;
	type?: string;
	label?: string;
}

export interface ImageRule {
	id: string;
	name: string;
	description?: string | null;
	rules: RuleItem[];
	created_at: string;
}

