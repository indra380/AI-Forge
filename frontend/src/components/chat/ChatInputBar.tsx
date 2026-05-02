import { useState } from "react";
import type { FormEvent } from "react";

interface ChatInputBarProps {
  disabled: boolean;
  onSend: (message: string) => Promise<void>;
}

export function ChatInputBar({ disabled, onSend }: ChatInputBarProps) {
  const [value, setValue] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = value.trim();
    if (!message || disabled) {
      return;
    }

    setValue("");
    await onSend(message);
  }

  return (
    <form onSubmit={handleSubmit} className="border-t border-slate-200 bg-white px-4 py-4">
      <div className="mx-auto flex w-full max-w-4xl items-end gap-3">
        <textarea
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="Ask anything..."
          className="min-h-24 flex-1 resize-y rounded-xl border border-slate-300 p-3 text-sm outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
        />
        <button
          type="submit"
          disabled={disabled || value.trim().length === 0}
          className="rounded-xl bg-slate-900 px-4 py-3 text-sm font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {disabled ? "Thinking..." : "Send"}
        </button>
      </div>
    </form>
  );
}
