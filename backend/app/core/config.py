from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    SECRET_KEY: str
    JWT_EXPIRE_MINUTES: int = 480
    APP_NAME: str = "amzur-ai-chat"
    ENVIRONMENT: str = "development"
    FRONTEND_URL: str = "http://localhost:5173"

    # Database
    DATABASE_URL: str

    # Amzur LiteLLM Proxy
    LITELLM_PROXY_URL: str = "https://litellm.amzur.com"
    LITELLM_API_KEY: str
    LLM_MODEL: str = "gemini/gemini-2.5-flash"
    LITELLM_EMBEDDING_MODEL: str = "text-embedding-3-large"
    IMAGE_PROVIDER: str = "openai"
    IMAGE_GEN_MODEL: str = "gemini/imagen-4.0-fast-generate-001"
    IMAGE_GEN_FALLBACK_MODEL: str = "gemini/imagen-4.0-fast-generate-001"
    IMAGE_RATE_LIMIT_PER_MINUTE: int = 20
    IMAGE_GENERATION_TIMEOUT: int = 60
    IMAGE_STORAGE: str = "local"
    IMAGE_OUTPUT_PATH: str = "./generated"

    # Upload storage backend
    UPLOAD_STORAGE: str = "local"

    # Google OAuth
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/auth/google/callback"

    # ChromaDB / RAG
    CHROMA_DB_PATH: str = "./chroma_db"
    CHROMA_ANONYMIZED_TELEMETRY: bool = False
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    TOP_K_RESULTS: int = 8
    MAX_PDF_SIZE_MB: int = 50

    # Google Sheets
    GOOGLE_SERVICE_ACCOUNT_JSON: Optional[str] = None

    # n8n onboarding automation
    N8N_ONBOARDING_ENABLED: bool = False
    N8N_ONBOARDING_WEBHOOK_URL: Optional[str] = None
    N8N_WEBHOOK_USER: Optional[str] = None
    N8N_WEBHOOK_PASSWORD: Optional[str] = None
    N8N_WEBHOOK_TIMEOUT_SECONDS: int = 5

    # MCP arXiv server (tool layer)
    ARXIV_MCP_COMMAND: str = "npx"
    ARXIV_MCP_ARGS: str = "-y arxiv-mcp-server/mcp-simple-arxiv"
    ARXIV_MCP_SEARCH_TOOL: Optional[str] = None
    ARXIV_MCP_DETAILS_TOOL: Optional[str] = None
    ARXIV_MCP_TIMEOUT_SECONDS: int = 4
    ARXIV_DIRECT_TIMEOUT_SECONDS: int = 4
    ARXIV_MCP_ONLY: bool = True
    # HTTP MCP server (preferred over stdio on Windows)
    ARXIV_MCP_HTTP_URL: Optional[str] = None
    ARXIV_MCP_SSE_URL: Optional[str] = None
    ARXIV_MCP_STORAGE_PATH: str = "./arxiv_papers"
    # When False, avoid synthetic paper results during rate limits.
    ARXIV_USE_MOCK_ON_RATE_LIMIT: bool = False

    # File uploads
    MAX_UPLOAD_MB: int = 50
    MAX_UPLOAD_SIZE_MB: int = 100
    UPLOAD_PATH: str = "./uploads"

    # Attachment MIME policy by category
    ATTACHMENT_IMAGE_MIME_TYPES: list[str] = [
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "image/svg+xml",
    ]
    ATTACHMENT_VIDEO_MIME_TYPES: list[str] = ["video/mp4", "video/webm", "video/quicktime"]
    ATTACHMENT_TABLE_MIME_TYPES: list[str] = [
        "text/csv",
        "application/json",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    ]
    ATTACHMENT_DOCUMENT_MIME_TYPES: list[str] = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "text/markdown",
    ]
    ATTACHMENT_CODE_MIME_TYPES: list[str] = [
        "text/plain",
        "text/markdown",
        "application/json",
        "application/javascript",
        "application/typescript",
        "text/x-python",
        "text/yaml",
        "text/html",
        "text/css",
        "text/x-java-source",
        "text/x-csharp",
        "text/x-c++src",
        "text/x-sql",
    ]
    ATTACHMENT_FORMULA_MIME_TYPES: list[str] = ["application/x-tex", "text/plain"]

    # NL-to-SQL / agent settings
    DATABASE_QUERY_TIMEOUT: int = 30
    MAX_SQL_ROWS: int = 500

    # Short-term memory tuning
    MAX_HISTORY_MESSAGES: int = 40
    MAX_CONTEXT_CHARS: int = 32000

    # Accepted MIME types (never hardcode these in handlers/services)
    ACCEPTED_MIME_TYPES: list[str] = [
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "video/mp4",
        "video/webm",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
        "text/plain",
        "text/csv",
    ]


settings = Settings()
