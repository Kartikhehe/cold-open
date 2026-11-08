import { useState, type FormEvent } from "react";
import { checkAccess, setAccessCode } from "../lib/api";

/** Asks once for the demo access code; kept in memory only, gone on refresh. */
export function AccessGate({ onDone }: { onDone?: () => void }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const value = code.trim();
    if (!value) {
      setError("Enter the access code you were given.");
      return;
    }
    setBusy(true);
    const ok = await checkAccess(value).catch(() => false);
    setBusy(false);
    if (!ok) {
      setError("That code did not match. Check it and try again.");
      return;
    }
    setAccessCode(value);
    onDone?.();
  }

  return (
    <div className="mx-auto mt-24 max-w-sm px-4">
      <form onSubmit={submit} className="rounded-panel border border-rule bg-console p-6">
        <h1 className="text-lg font-semibold">Enter access code</h1>
        <p className="mt-1 text-sm text-fog">The demo runs contain a client's scripts, so they are behind a code.</p>
        <label htmlFor="code" className="mt-5 block text-sm">Access code</label>
        <input
          id="code"
          name="access-code"
          type="password"
          autoComplete="off"
          spellCheck={false}
          autoFocus
          value={code}
          onChange={(e) => setCode(e.target.value)}
          aria-invalid={!!error}
          aria-describedby={error ? "code-error" : undefined}
          className="mt-1 w-full rounded-chip border border-rule bg-bay px-3 py-2 text-md"
        />
        {error && (
          <p id="code-error" className="mt-2 text-sm text-rec-ink">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={busy}
          className="mt-5 w-full rounded-chip bg-tungsten px-4 py-2 font-semibold text-ink transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          {busy ? "Checking…" : "Open the cutting room"}
        </button>
      </form>
    </div>
  );
}
