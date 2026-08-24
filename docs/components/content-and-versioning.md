# Content and versioning component

Core block types: heading, paragraph, ordered/unordered procedure, objective list, warning/note, table, figure/asset placeholder, quiz/checklist, and source list. Each block has stable ID, order key, typed payload, citations, provenance, and version metadata.

Content versions and outline versions are immutable snapshots or immutable versioned block membership. Project current pointers change transactionally. Provenance records run/tool/subagent, prompt/model profile, pinned sources/skills/retrieval/evaluator config, and parent version.

Queries return bounded module/block views. Required tests: schema per block type, ordering, immutable history, citation targets, copy-on-version behavior, current-pointer race, project isolation, provenance completeness, and render compatibility.
