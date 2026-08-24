# System context

Groundloom serves authors, reviewers, workspace administrators, and operators. The web client talks only to the FastAPI product boundary. That boundary coordinates domain services and the agent runtime; neither is exposed directly to the browser.

External dependencies are model providers, object storage, email/identity provider when selected, malware/OCR/parser services where configured, and Langfuse. Each is behind a narrow adapter with timeouts, typed errors, telemetry, and a test fake.

Trust boundaries:

1. Browser input and uploaded documents are untrusted.
2. API identity/runtime context is trusted only after authentication and membership resolution.
3. Model output is untrusted until schema and policy validation.
4. Domain services are the only path to canonical state.
5. Workers operate with scoped service identity and leased jobs.

**ARCH-CTX-001:** No frontend, model, or framework checkpoint may bypass the product/service boundary to mutate canonical state.
