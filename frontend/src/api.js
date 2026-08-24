/** @typedef {{method?: string, headers?: Record<string, string>, body?: BodyInit}} RequestOptions */

const API = import.meta.env?.VITE_API_URL || "http://127.0.0.1:8000";
const EXPORT_POLL_INTERVAL_MS = 500;
const EXPORT_POLL_ATTEMPTS = 30;

/** @param {RequestOptions} options */
function requestHeaders(options) {
  return {
    "Content-Type": "application/json",
    "X-User-ID": "local-user",
    "X-Workspace-ID": "local-workspace",
    "X-Correlation-ID": globalThis.crypto?.randomUUID?.() || "local-correlation",
    ...(options.headers || {}),
  };
}

async function waitForExport(job) {
  if (!["queued", "rendering", "storing"].includes(job.status)) return job;
  for (let attempt = 0; attempt < EXPORT_POLL_ATTEMPTS; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, EXPORT_POLL_INTERVAL_MS));
    const current = await api(`/v1/exports/${job.id}`);
    if (current.status === "completed") return current;
    if (["failed", "cancelled", "expired"].includes(current.status)) {
      const error = new Error("The export could not be completed.");
      error.code = current.error_code || "EXPORT_FAILED";
      error.retryable = current.status === "failed";
      throw error;
    }
  }
  const error = new Error("The export is still processing. Retry status shortly.");
  error.code = "EXPORT_PENDING";
  error.retryable = true;
  throw error;
}

/** @template T @param {string} path @param {RequestOptions} [options] @returns {Promise<T>} */
export async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: requestHeaders(options),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.message || "The request could not be completed.");
    error.code = data.code;
    error.retryable = Boolean(data.retryable);
    throw error;
  }
  if (path === "/v1/exports" && options.method === "POST") {
    return /** @type {T} */ (await waitForExport(data));
  }
  return /** @type {T} */ (data);
}

/**
 * Subscribe to the finite SSE replay endpoint and reconnect with the last
 * durable event ID. Returns an abort function.
 * @param {string} path
 * @param {(event: any) => void} onEvent
 * @param {(state: string) => void} [onStatus]
 */
export function subscribeToEvents(path, onEvent, onStatus = () => {}) {
  let stopped = false;
  let cursor = "";
  let activeController;
  let retry = 0;

  const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
  const consume = async () => {
    while (!stopped) {
      activeController = new AbortController();
      try {
        onStatus(cursor ? "reconnecting" : "connecting");
        const response = await fetch(`${API}${path}`, {
          headers: requestHeaders({
            headers: cursor ? { "Last-Event-ID": cursor } : {},
          }),
          signal: activeController.signal,
        });
        if (!response.ok || !response.body) throw new Error("event stream unavailable");
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        onStatus("connected");
        while (!stopped) {
          const chunk = await reader.read();
          if (chunk.done) break;
          buffer += decoder.decode(chunk.value, { stream: true });
          const frames = buffer.split("\n\n");
          buffer = frames.pop() || "";
          for (const frame of frames) {
            const id = frame.match(/^id: (.+)$/m)?.[1];
            const data = frame.match(/^data: (.+)$/m)?.[1];
            if (id) cursor = id;
            if (data) onEvent(JSON.parse(data));
          }
        }
        retry = 0;
      } catch (error) {
        if (stopped) break;
        retry += 1;
        onStatus("reconnecting");
        await wait(Math.min(1000 * 2 ** Math.min(retry, 3), 5000));
      }
      if (!stopped) await wait(2000);
    }
  };
  consume();
  return () => {
    stopped = true;
    activeController?.abort();
    onStatus("offline");
  };
}

export { API };
