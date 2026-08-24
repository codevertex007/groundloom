# Versioning contract

Version immutable sources, skills, project configuration, outlines/content, templates, prompts, tool schemas, model profiles, retrieval configuration, rubrics/evaluators, public events, and APIs.

Runs record exact immutable IDs or content hashes before consequential output. Additive API/event fields are compatible; removed/renamed/semantic changes require a new version and compatibility window. Tool schema changes require an agent-definition version and resume compatibility decision. Published skill/content/source bytes never change under the same version ID.

Migrations define how old runs resume or fail safely, how historical artifacts render, and how evaluation comparison remains meaningful. Do not pretend exact model nondeterminism is reproducibility; preserve enough inputs/configuration to diagnose and re-evaluate.
