# AI Forge

AI Forge is an internal multi-user conversational AI platform with a React frontend, a FastAPI backend, persistent chat threads, document-aware AI workflows, Google OAuth, onboarding automation, and research tooling.

## Repository layout

- `frontend/`: React 18 + TypeScript + Vite client
- `backend/`: FastAPI application, Alembic migrations, services, AI orchestration, and onboarding hooks
- `Chatbot Registration Workflow - GChat - updated.json`: importable n8n workflow for user onboarding notifications

## Key capabilities

- Email/password and Google OAuth authentication
- Persistent threaded chat and conversational memory
- RAG over uploaded files and datasets
- AI image generation through the LiteLLM proxy
- Research paper persistence for digest flows
- n8n-driven user onboarding with Gmail and Google Chat notifications

## Local development

### Backend

1. Create and activate a Python 3.11+ virtual environment.
2. Install dependencies from `backend/requirements.txt`.
3. Configure `backend/.env` with database, LiteLLM, auth, and onboarding settings.
4. Run migrations with Alembic.
5. Start the API from `backend/`:

```powershell
uvicorn app.main:app --reload
```

### Frontend

1. Install dependencies from `frontend/package.json`.
2. Start the Vite dev server from `frontend/`:

```powershell
npm install
npm run dev
```

## n8n onboarding workflow

Import `Chatbot Registration Workflow - GChat - updated.json` into n8n Cloud.

Before activating it:

1. Configure the Postgres, Gmail, and Google OAuth credentials in n8n.
2. Replace the placeholder Google Chat webhook URL in the workflow with your live incoming webhook URL.
3. Verify the backend webhook URL matches `N8N_ONBOARDING_WEBHOOK_URL` in `backend/.env`.

## Notes

- All AI requests must go through the Amzur LiteLLM proxy.
- Do not commit live `.env` files, generated credentials, or local runtime logs.