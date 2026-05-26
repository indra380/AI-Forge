import { useEffect, useMemo, useState } from "react";

import { getTicTacToeState, playTicTacToeMove, startTicTacToe } from "../../lib/api";
import type { TicTacToeState } from "../../types";

interface TicTacToePanelProps {
  threadId: string | null;
}

function statusText(state: TicTacToeState | null, loading: boolean): string {
  if (!state) return loading ? "Loading game..." : "Start a game to play.";
  if (loading) return "Agent thinking...";
  if (state.winner === "X") return "You win!";
  if (state.winner === "O") return "Agent wins.";
  if (state.winner === "draw") return "It’s a draw.";
  if (!state.active) return "Start a game to play.";
  return "Your turn (X)";
}

export function TicTacToePanel({ threadId }: TicTacToePanelProps) {
  const [state, setState] = useState<TicTacToeState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadState() {
      if (!threadId) {
        setState(null);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const next = await getTicTacToeState(threadId);
        setState(next);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to load game state.";
        setError(message);
      } finally {
        setLoading(false);
      }
    }
    void loadState();
  }, [threadId]);

  const board = state?.board ?? Array(9).fill(" ");
  const status = useMemo(() => statusText(state, loading), [state, loading]);

  async function resetBoard() {
    if (!threadId) return;
    setLoading(true);
    setError(null);
    try {
      const next = await startTicTacToe(threadId);
      setState(next);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to start game.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  async function handleCellClick(index: number) {
    if (!threadId || loading || board[index] !== " ") return;
    setLoading(true);
    setError(null);
    try {
      let current = state;
      if (!current?.active || current.winner) {
        current = await startTicTacToe(threadId);
      }
      if (!current.active) {
        throw new Error("Game is not active.");
      }
      const next = await playTicTacToeMove(threadId, { position: index + 1 });
      setState(next);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Move failed.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="flex flex-1 items-center justify-center p-6">
      <div className="w-full max-w-xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Tic Tac Toe Agent</h2>
            <p className="text-sm text-slate-500">Click a cell to play as X against the backend agent.</p>
          </div>
          <button
            type="button"
            onClick={resetBoard}
            disabled={!threadId || loading}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
          >
            New Game
          </button>
        </div>

        {!threadId ? (
          <div className="mb-4 rounded-lg bg-amber-100 px-3 py-2 text-sm font-medium text-amber-800">
            Create or select a chat thread first to play.
          </div>
        ) : null}
        {error ? (
          <div className="mb-4 rounded-lg bg-red-100 px-3 py-2 text-sm font-medium text-red-700">
            {error}
          </div>
        ) : null}
        <div className="mb-4 rounded-lg bg-slate-100 px-3 py-2 text-sm font-medium text-slate-700">
          {status}
        </div>

        <div className="grid grid-cols-3 gap-2">
          {board.map((rawCell, idx) => {
            const cell = rawCell === " " ? "" : rawCell;
            return (
            <button
              key={idx}
              type="button"
              onClick={() => handleCellClick(idx)}
              disabled={!threadId || loading || !state?.active || state.winner !== null || cell !== ""}
              className="flex h-24 items-center justify-center rounded-xl border border-slate-300 bg-slate-50 text-3xl font-bold text-slate-800 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-80"
            >
              {cell || " "}
            </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}
