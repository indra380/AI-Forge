import { useEffect, useRef, useState } from "react";
import type { DbConnection } from "../../types";
import { createDbConnection, getDbConnections, setThreadDbConnection } from "../../lib/api";

interface DatabaseConnectModalProps {
  threadId: string | null;
  onClose: () => void;
  onConnected: (conn: DbConnection) => void;
}

const DB_TYPES = [
  { value: "postgresql", label: "PostgreSQL" },
  { value: "mysql", label: "MySQL" },
  { value: "sqlite", label: "SQLite" },
  { value: "mssql", label: "SQL Server (MSSQL)" },
];

export function DatabaseConnectModal({
  threadId,
  onClose,
  onConnected,
}: DatabaseConnectModalProps) {
  const [tab, setTab] = useState<"new" | "existing">("new");
  const [dbType, setDbType] = useState("postgresql");
  const [host, setHost] = useState("localhost");
  const [port, setPort] = useState("5432");
  const [database, setDatabase] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [existing, setExisting] = useState<DbConnection[]>([]);

  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (tab === "existing") {
      getDbConnections()
        .then(setExisting)
        .catch(() => {});
    }
  }, [tab]);

  useEffect(() => {
    const portMap: Record<string, string> = {
      postgresql: "5432",
      mysql: "3306",
      mssql: "1433",
      sqlite: "",
    };
    setPort(portMap[dbType] ?? "5432");
  }, [dbType]);

  async function handleCreate() {
    if (!name.trim()) {
      setError("Connection name is required.");
      return;
    }
    if (dbType !== "sqlite" && !database.trim()) {
      setError("Database name is required.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const conn = await createDbConnection({
        name,
        db_type: dbType,
        host: dbType !== "sqlite" ? host : undefined,
        port: port ? parseInt(port) : undefined,
        database,
        username: username || undefined,
        password: password || undefined,
      });
      if (threadId) {
        await setThreadDbConnection(threadId, conn.id);
      }
      onConnected(conn);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: { message?: string } | string } } };
      const detail = e.response?.data?.detail;
      setError(
        typeof detail === "object" && detail?.message
          ? detail.message
          : typeof detail === "string"
          ? detail
          : "Failed to connect. Check credentials."
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleUseExisting(conn: DbConnection) {
    if (!threadId) {
      onConnected(conn);
      return;
    }
    setLoading(true);
    try {
      await setThreadDbConnection(threadId, conn.id);
      onConnected(conn);
    } catch {
      setError("Failed to activate connection.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
    >
      <div className="w-full max-w-md rounded-2xl bg-white shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h2 className="text-base font-semibold text-slate-800">
            Connect Database
          </h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600"
          >
            ✕
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-slate-100">
          {(["new", "existing"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`flex-1 py-2.5 text-sm font-medium transition-colors ${
                tab === t
                  ? "border-b-2 border-slate-800 text-slate-800"
                  : "text-slate-400 hover:text-slate-600"
              }`}
            >
              {t === "new" ? "New Connection" : "Saved Connections"}
            </button>
          ))}
        </div>

        <div className="p-5">
          {tab === "new" ? (
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">
                  Connection Name *
                </label>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Production DB"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400 focus:ring-1 focus:ring-slate-200"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">
                  Database Type *
                </label>
                <select
                  value={dbType}
                  onChange={(e) => setDbType(e.target.value)}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
                >
                  {DB_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </div>
              {dbType !== "sqlite" && (
                <>
                  <div className="flex gap-2">
                    <div className="flex-1">
                      <label className="block text-xs font-medium text-slate-600 mb-1">
                        Host
                      </label>
                      <input
                        value={host}
                        onChange={(e) => setHost(e.target.value)}
                        placeholder="localhost"
                        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
                      />
                    </div>
                    <div className="w-24">
                      <label className="block text-xs font-medium text-slate-600 mb-1">
                        Port
                      </label>
                      <input
                        value={port}
                        onChange={(e) => setPort(e.target.value)}
                        placeholder="5432"
                        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">
                      Database Name *
                    </label>
                    <input
                      value={database}
                      onChange={(e) => setDatabase(e.target.value)}
                      placeholder="mydb"
                      className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
                    />
                  </div>
                  <div className="flex gap-2">
                    <div className="flex-1">
                      <label className="block text-xs font-medium text-slate-600 mb-1">
                        Username
                      </label>
                      <input
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        placeholder="admin"
                        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
                      />
                    </div>
                    <div className="flex-1">
                      <label className="block text-xs font-medium text-slate-600 mb-1">
                        Password
                      </label>
                      <input
                        type="password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="••••••"
                        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
                      />
                    </div>
                  </div>
                </>
              )}
              {dbType === "sqlite" && (
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">
                    Database File Path *
                  </label>
                  <input
                    value={database}
                    onChange={(e) => setDatabase(e.target.value)}
                    placeholder="/path/to/mydb.sqlite"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
                  />
                </div>
              )}
              {error && (
                <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-600">
                  {error}
                </p>
              )}
              <button
                onClick={handleCreate}
                disabled={loading}
                className="mt-1 w-full rounded-lg bg-slate-900 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:opacity-50"
              >
                {loading ? "Connecting…" : "Connect & Activate"}
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              {existing.length === 0 && (
                <p className="text-center text-sm text-slate-400 py-6">
                  No saved connections yet.
                </p>
              )}
              {existing.map((conn) => (
                <button
                  key={conn.id}
                  onClick={() => handleUseExisting(conn)}
                  className="w-full flex items-center gap-3 rounded-xl border border-slate-200 px-4 py-3 text-left hover:border-slate-400 hover:bg-slate-50 transition"
                >
                  <span className="text-xl">🗄️</span>
                  <div>
                    <div className="text-sm font-medium text-slate-800">
                      {conn.name}
                    </div>
                    <div className="text-xs text-slate-400">
                      {conn.db_type}
                      {conn.host ? ` · ${conn.host}` : ""}
                      {conn.database ? `/${conn.database}` : ""}
                    </div>
                  </div>
                </button>
              ))}
              {error && (
                <p className="text-sm text-rose-600">{error}</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
