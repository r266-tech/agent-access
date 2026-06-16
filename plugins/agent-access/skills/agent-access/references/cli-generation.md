# CLI Generation Reference

Read this when a stable, repeatable website/API/GUI workflow does not yet have an agent-native CLI, or when an existing CLI needs systematic improvement.

## When To Print A CLI

Create or improve a CLI when:

- the same site, API, app, or file workflow will be queried repeatedly;
- browser exploration found a stable endpoint, embedded data shape, GraphQL shape, request body, or pagination pattern;
- local software exposes a script API, plugin API, project file, or import/export format;
- an agent needs multi-step composition and browser clicks are wasteful or hard to reproduce;
- login/session is needed but the data path after login is stable;
- an existing CLI mostly works but is awkward for agents.

## Research Before Build

Start with:

1. Official docs, OpenAPI/GraphQL schema, SDKs, or source.
2. Existing open-source CLIs, MCP servers, wrappers, or user scripts.
3. Network requests, embedded JSON, RSS, SSR data, or JSON-LD.
4. Software script APIs, plugin systems, project file formats, and import/export formats.
5. Similar CLI patterns for auth, pagination, caching, rate limits, dry-run, and errors.

## Agent-Native Contract

A CLI should have:

- useful `--help`;
- safe read defaults;
- explicit write flags or dry-run;
- stable JSON stdout and deterministic exit codes;
- errors with `next_action`;
- stable IDs, URLs, cursors, or cache refs for follow-up;
- scriptable limit, cursor/page, filter, sort, and fields;
- `doctor` or equivalent diagnostics;
- realistic dogfood proof.

## Build Loop

1. Define minimal spec: target, auth, data source, commands, output schema.
2. Implement the smallest useful path.
3. Dogfood with the real agent task.
4. Fix friction.
5. Move stable findings into CLI code.
6. Put browser-only traps into focused references.
7. Update the registry and verification evidence.
