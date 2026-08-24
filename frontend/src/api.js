/** @typedef {{method?: string, headers?: Record<string, string>, body?: BodyInit}} RequestOptions */

const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

/** @param {RequestOptions} options */
function requestHeaders(options) {
  return {
    "Content-Type": "application/json",
    "X-User-ID": "local-user",
    "X-Workspace-ID": "local-workspace",
    "X-Correlation-ID": crypto.randomUUID(),
    ...(options.headers || {}),
  };
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
  return /** @type {T} */ (data);
}

export { API };
