# AI frontend boundary

AI-specific presentation belongs in this folder. `AgentEventLabel` is kept
small and deterministic: it renders only bounded metadata from the durable
agent event contract. Backend transport remains in `src/api.js`, while
canonical project and content screens remain in `src/main.jsx`.

Future AI UI contributions should add focused components here and consume
typed API/event data rather than embedding provider-specific behavior in
screen composition.
