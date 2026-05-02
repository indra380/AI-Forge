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
    IMAGE_GEN_MODEL: str = "gemini/imagen-4.0-fast-generate-001"

    # Google OAuth
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/auth/google/callback"

    # ChromaDB
    CHROMA_PERSIST_DIR: str = "./chroma_db"

    # Google Sheets
    GOOGLE_SERVICE_ACCOUNT_JSON: Optional[str] = None

    # File uploads
    MAX_UPLOAD_MB: int = 20
    UPLOAD_DIR: str = "./uploads"

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
