# Backend

The backend is a FastAPI application structured around routers, services, SQLAlchemy models, and Pydantic schemas.

## Main responsibilities

- Authentication with email/password and Google OAuth
- Threaded chat APIs and persistence
- RAG, research, and AI orchestration services
- n8n onboarding webhook triggers for new-user automation
- Alembic-managed PostgreSQL schema migrations

## Run locally

1. Create a Python 3.11+ virtual environment.
2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Configure `.env` with at least:

- `DATABASE_URL`
- `SECRET_KEY`
- `LITELLM_API_KEY`
- `LITELLM_PROXY_URL`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `N8N_ONBOARDING_ENABLED`
- `N8N_ONBOARDING_WEBHOOK_URL`

4. Apply migrations:

```powershell
alembic upgrade head
```

5. Start the API:

```powershell
uvicorn app.main:app --reload
```

## Recent additions

- Research paper persistence via `research_papers`
- Fail-open onboarding automation service for n8n
- User onboarding log table and related migration support
- Windows asyncio shutdown-noise suppression during development

## Testing

Run backend tests from `backend/`:

```powershell
pytest
```