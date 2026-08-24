import test from "node:test";
import assert from "node:assert/strict";
import { api, subscribeToEvents } from "./api.js";

test("api exposes typed product errors and correlation headers", async () => {
  const originalFetch = globalThis.fetch;
  let received;
  globalThis.fetch = async (_url, options) => {
    received = options;
    return new Response(JSON.stringify({ code: "DEPENDENCY_UNAVAILABLE", message: "retry", retryable: true }), {
      status: 503,
      headers: { "content-type": "application/json" },
    });
  };
  await assert.rejects(() => api("/v1/health"), (error) => {
    assert.equal(error.code, "DEPENDENCY_UNAVAILABLE");
    assert.equal(error.retryable, true);
    return true;
  });
  assert.equal(received.headers["X-Workspace-ID"], "local-workspace");
  assert.ok(received.headers["X-Correlation-ID"]);
  globalThis.fetch = originalFetch;
});

test("SSE reconnect resumes from the last durable event id without duplicate parsing", async () => {
  const originalFetch = globalThis.fetch;
  const requests = [];
  let calls = 0;
  const stream = (frames) => new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(frames));
      controller.close();
    },
  });
  globalThis.fetch = async (_url, options) => {
    requests.push(options.headers["Last-Event-ID"] || "");
    calls += 1;
    const id = calls === 1 ? "evt-1" : "evt-2";
    const type = calls === 1 ? "one" : "two";
    return new Response(stream(`id: ${id}\ndata: ${JSON.stringify({ type })}\n\n`), { status: 200 });
  };
  const events = [];
  const statuses = [];
  let stop;
  stop = subscribeToEvents("/v1/threads/thread/events/stream", (event) => {
    events.push(event);
    if (events.length === 2) stop();
  }, (status) => statuses.push(status));
  await new Promise((resolve) => setTimeout(resolve, 2300));
  assert.deepEqual(events, [{ type: "one" }, { type: "two" }]);
  assert.deepEqual(requests.slice(0, 2), ["", "evt-1"]);
  assert.ok(statuses.includes("offline"));
  globalThis.fetch = originalFetch;
});
