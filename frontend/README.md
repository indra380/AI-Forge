# Frontend

The frontend is a React 18 + TypeScript application built with Vite.

## Responsibilities

- Authentication flows and session-aware UI
- Chat threads, messaging, and streaming responses
- File upload and multimodal interaction surfaces
- Research, RAG, and image-generation user flows

## Development

Install dependencies and run the app from `frontend/`:

```powershell
npm install
npm run dev
```

## Build

```powershell
npm run build
```

## Conventions

- React functional components with TypeScript strict mode
- Shared API access through `src/lib/`
- Shared types in `src/types/`
- Tailwind-based UI styling

## Environment

Ensure the frontend is configured to point to the backend API URL used by your local or deployed FastAPI service.
