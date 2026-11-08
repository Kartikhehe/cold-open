/** API client. The access code lives in memory only (never localStorage), as the brief requires. */
let accessCode: string | null = null;
const listeners = new Set<() => void>();

export const getAccessCode = () => accessCode;
export function setAccessCode(code: string | null) {
  accessCode = code;
  cache.clear();
  listeners.forEach((l) => l());
}
export function onAuthChange(fn: () => void) {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function headers(extra: Record<string, string> = {}) {
  const h: Record<string, string> = { ...extra };
  if (accessCode) h["X-Access-Code"] = accessCode;
  return h;
}

const cache = new Map<string, Promise<unknown>>();

async function fail(r: Response): Promise<never> {
  const body = await r.json().catch(() => ({}));
  throw new ApiError(r.status, typeof body.detail === "string" ? body.detail : r.statusText);
}

export function get<T>(path: string, fresh = false): Promise<T> {
  if (!fresh && cache.has(path)) return cache.get(path) as Promise<T>;
  const p = fetch(path, { headers: headers() }).then((r) => (r.ok ? (r.json() as Promise<T>) : fail(r)));
  p.catch(() => cache.delete(path));
  cache.set(path, p);
  return p;
}

export async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method: "POST",
    headers: headers({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  return r.ok ? (r.json() as Promise<T>) : fail(r);
}

export async function checkAccess(code: string): Promise<boolean> {
  const r = await fetch("/api/access", { method: "POST", headers: { "X-Access-Code": code } });
  return r.ok;
}

export function invalidate(prefix: string) {
  for (const k of [...cache.keys()]) if (k.startsWith(prefix)) cache.delete(k);
}

export function exportUrl(runId: string, name: string) {
  const q = accessCode ? `?code=${encodeURIComponent(accessCode)}` : "";
  return `/api/runs/${runId}/export/${name}${q}`;
}

export async function upload(form: FormData): Promise<{ job_id: string; run_id: string; run_token: string }> {
  const r = await fetch("/api/runs", { method: "POST", headers: headers(), body: form });
  return r.ok ? r.json() : fail(r);
}
