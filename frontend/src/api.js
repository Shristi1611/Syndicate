// One place that knows where the backend lives and how to talk to it.
export const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

const TIMEOUT_MS = 8000; // give up on a request that hangs, so the screen never freezes

async function request(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    ...options,
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `The server returned ${res.status}`);
  }
  return res.json();
}

export const get = (path) => request(path);

export const post = (path, body) =>
  request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });