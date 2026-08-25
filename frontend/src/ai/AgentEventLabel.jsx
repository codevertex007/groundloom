import React from "react";

/**
 * Renders bounded, user-safe metadata from a durable agent event.
 * Model text, tool arguments, and source passages never belong in this view.
 */
export function AgentEventLabel({ event }) {
  const payload = event?.payload || {};
  const detail =
    payload.summary ||
    (payload.tool_name &&
      `${payload.tool_name}${payload.node ? ` · ${payload.node}` : ""}`) ||
    (payload.node && `Agent node · ${payload.node}`) ||
    payload.name ||
    payload.text ||
    event?.type ||
    "Agent activity";
  return <>{detail}</>;
}
