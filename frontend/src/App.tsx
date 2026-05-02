import { useMutation } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { ChatInputBar } from "./components/chat/ChatInputBar";
import { ChatMessageList } from "./components/chat/ChatMessageList";
import { ThreadSidebar } from "./components/chat/ThreadSidebar";
import { useChat } from "./hooks/useChat";
import {
  createThread,
  deleteThread,
  getGoogleLoginUrl,
  getThreadMessages,
  getThreads,
  login,
  logout,
  me,
  register,
  renameThread,
} from "./lib/api";
import type { AuthUser, ChatThread } from "./types";

export default function App() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authError, setAuthError] = useState<string | null>(null);

  const [threads, setThreads] = useState<ChatThread[]>([]);

  const handleThreadRenamed = useCallback((threadId: string, title: string) => {
    setThreads((prev) =>
      prev.map((t) => (t.id === threadId ? { ...t, title } : t))
    );
  }, []);

  const { messages, hasMessages, setMessages, activeThreadId, setActiveThreadId, sendMessage, sendMessageToThread, isStreaming } =
    useChat((title) => {
      // onThreadRenamedRef in useChat always holds the latest activeThreadId via closure refresh
      if (activeThreadId) handleThreadRenamed(activeThreadId, title);
    });

  // Prevent message-clear flicker on new thread (KI-02)
  const justCreatedRef = useRef(false);

  function resolveAuthError(error: unknown): string {
    if (error !== null && typeof error === "object" && "response" in error) {
      const axiosError = error as {
        response?: { data?: { detail?: { message?: string } | string } };
      };
      const detail = axiosError.response?.data?.detail;
      if (detail && typeof detail === "object" && detail.message) return detail.message;
      if (typeof detail === "string") return detail;
    }
    return "Authentication failed. Please try again.";
  }

  function validateAuthForm(): string | null {
    if (!email.endsWith("@amzur.com")) return "Only @amzur.com email addresses are allowed.";
    if (password.length < 8) return "Password must be at least 8 characters.";
    return null;
  }

  async function loadThreads() {
    const fetched = await getThreads();
    setThreads(fetched);
    return fetched;
  }

  async function selectThread(thread: ChatThread) {
    setActiveThreadId(thread.id);
    const msgs = await getThreadMessages(thread.id);
    setMessages(msgs);
  }

  async function handleNewThread() {
    const thread = await createThread();
    justCreatedRef.current = true;
    setThreads((prev) => [thread, ...prev]);
    setActiveThreadId(thread.id);
    setMessages([]);
  }

  async function handleDeleteThread(threadId: string) {
    await deleteThread(threadId);
    setThreads((prev) => prev.filter((t) => t.id !== threadId));
    if (activeThreadId === threadId) {
      setActiveThreadId(null);
      setMessages([]);
    }
  }

  async function handleRenameThread(threadId: string, title: string) {
    await renameThread(threadId, title);
    handleThreadRenamed(threadId, title);
  }

  const authMutation = useMutation({
    mutationFn: async () => {
      const payload = { email, password };
      if (authMode === "register") await register(payload);
      return login(payload);
    },
    onSuccess: async (authUser) => {
      setUser(authUser);
      setAuthError(null);
      const fetched = await loadThreads();
      if (fetched.length > 0) {
        await selectThread(fetched[0]);
      }
    },
    onError: (error: unknown) => {
      setAuthError(resolveAuthError(error));
    },
  });

  useEffect(() => {
    // Handle ?auth_error= from Google OAuth redirect
    const params = new URLSearchParams(window.location.search);
    const oauthError = params.get("auth_error");
    if (oauthError) {
      setAuthError(decodeURIComponent(oauthError));
      window.history.replaceState({}, "", window.location.pathname);
    }

    async function bootstrap() {
      try {
        const authUser = await me();
        setUser(authUser);
        const fetched = await loadThreads();
        if (fetched.length > 0) await selectThread(fetched[0]);
      } catch {
        setUser(null);
      }
    }
    void bootstrap();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleAuthSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const validationError = validateAuthForm();
    if (validationError) {
      setAuthError(validationError);
      return;
    }
    setAuthError(null);
    await authMutation.mutateAsync();
  }

  async function handleLogout() {
    await logout();
    setUser(null);
    setMessages([]);
    setThreads([]);
    setActiveThreadId(null);
  }

  async function handleSend(message: string) {
    if (!activeThreadId) {
      // Auto-create a thread, then send directly with explicit threadId
      // (cannot use sendMessage here — setActiveThreadId is async, state not yet updated)
      const thread = await createThread();
      justCreatedRef.current = true;
      setThreads((prev) => [thread, ...prev]);
      setActiveThreadId(thread.id);
      await sendMessageToThread(message, thread.id);
    } else {
      await sendMessage(message);
    }
  }

  if (!user) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-linear-to-b from-slate-100 to-slate-200 p-4 text-slate-900">
        <form
          onSubmit={handleAuthSubmit}
          className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <h1 className="text-xl font-semibold tracking-tight">Amzur Employee Login</h1>
          <p className="mt-1 text-sm text-slate-600">Sign in with your @amzur.com account</p>

          <label className="mt-4 block text-sm font-medium text-slate-700">Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 p-2.5 text-sm outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
            placeholder="name@amzur.com"
            required
          />

          <label className="mt-3 block text-sm font-medium text-slate-700">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 p-2.5 text-sm outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
            required
          />

          {authError ? <p className="mt-3 text-sm text-red-600">{authError}</p> : null}

          <button
            type="submit"
            className="mt-4 w-full rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
            disabled={authMutation.isPending}
          >
            {authMutation.isPending
              ? "Please wait..."
              : authMode === "login"
                ? "Sign In"
                : "Register & Sign In"}
          </button>

          <div className="mt-3 flex items-center gap-2">
            <div className="h-px flex-1 bg-slate-200" />
            <span className="text-xs text-slate-400">or</span>
            <div className="h-px flex-1 bg-slate-200" />
          </div>

          <a
            href={getGoogleLoginUrl()}
            className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" aria-hidden="true">
              <path
                fill="#4285F4"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="#34A853"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="#FBBC05"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"
              />
              <path
                fill="#EA4335"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              />
            </svg>
            Sign in with Google
          </a>

          <button
            type="button"
            onClick={() => setAuthMode((prev) => (prev === "login" ? "register" : "login"))}
            className="mt-3 w-full text-sm text-slate-700 underline"
          >
            {authMode === "login" ? "Need an account? Register" : "Already have an account? Sign In"}
          </button>
        </form>
      </main>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-slate-100 text-slate-900">
      <ThreadSidebar
        threads={threads}
        activeThreadId={activeThreadId}
        onSelect={selectThread}
        onNew={handleNewThread}
        onRename={handleRenameThread}
        onDelete={handleDeleteThread}
      />

      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="border-b border-slate-200 bg-white/80 px-4 py-3 backdrop-blur">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-lg font-semibold tracking-tight">Amzur AI Chat</h1>
              <p className="text-xs text-slate-500">{user.email}</p>
            </div>
            <div className="flex items-center gap-3">
              {isStreaming && (
                <span className="rounded-full bg-slate-900 px-3 py-1 text-xs font-medium text-white">
                  Streaming…
                </span>
              )}
              <button
                type="button"
                onClick={handleLogout}
                className="rounded-full border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100"
              >
                Logout
              </button>
            </div>
          </div>
        </header>

        {!activeThreadId ? (
          <section className="flex flex-1 items-center justify-center">
            <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
              <h2 className="text-lg font-semibold">Start a new chat</h2>
              <p className="mt-2 text-sm text-slate-500">
                Type a message below or click <strong>+ New</strong> in the sidebar.
              </p>
            </div>
          </section>
        ) : !hasMessages ? (
          <section className="flex flex-1 items-center justify-center">
            <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
              <h2 className="text-lg font-semibold">Start the conversation</h2>
              <p className="mt-2 text-sm text-slate-500">
                Ask anything — responses stream token-by-token.
              </p>
            </div>
          </section>
        ) : (
          <ChatMessageList messages={messages} />
        )}

        <ChatInputBar disabled={isStreaming} onSend={handleSend} />
      </div>
    </div>
  );
}

