# Agent Access

Agent Access is a Codex plugin and thin access layer for agents. It helps an agent discover and use the right capability surface for a website, API, local app, GUI workflow, or recurring online task.

## Principles

- Keep the default skill small. Load references only when needed.
- Prefer agent-native CLIs and structured APIs before browser or GUI automation.
- Treat browser/CDP and Computer Use as exploration or fallback paths.
- Turn stable repeated workflows into CLIs.
- Keep auth/session handling explicit and local.
- Never upload usage experience, logs, screenshots, cookies, tokens, account identifiers, or local paths without explicit review and confirmation.

## What This Repository Includes

- `plugins/agent-access/.codex-plugin/plugin.json`: Codex plugin manifest.
- `plugins/agent-access/skills/agent-access/SKILL.md`: thin router instructions for agents.
- `plugins/agent-access/skills/agent-access/registry.example.json`: example companion CLI registry shape.
- `plugins/agent-access/skills/agent-access/scripts/agent-access.mjs`: local registry/auth/contribution helper.
- `plugins/agent-access/skills/agent-access/references/`: CLI generation, registry, auth/session, contribution, routing, and safe browser fallback references.
- `.agents/plugins/marketplace.json`: local/Git marketplace metadata for Codex App.
- `SECURITY.md`, `CONTRIBUTING.md`, and `LICENSE`.

This public core intentionally does not include private site-patterns, user run logs, screenshots, credentials, browser sessions, local CLI binaries, or personal/company packs.

## Quick Start

```bash
node plugins/agent-access/skills/agent-access/scripts/agent-access.mjs list
node plugins/agent-access/skills/agent-access/scripts/agent-access.mjs info example
node plugins/agent-access/skills/agent-access/scripts/agent-access.mjs doctor
node plugins/agent-access/skills/agent-access/scripts/agent-access.mjs audit-public .
```

## Install In Codex App

From a local checkout:

```bash
codex plugin marketplace add .
codex plugin add agent-access --marketplace agent-access
```

From GitHub after publishing:

```bash
codex plugin marketplace add r266-tech/agent-access --ref main
codex plugin add agent-access --marketplace agent-access
```

Use `AGENT_ACCESS_REGISTRY` to point at your own registry file when wiring companion CLIs.
The package also declares an `agent-access` bin for local development tools that install package bins.

## Companion CLI Contract

Recommended companion CLIs should provide:

- stable JSON stdout for machine use;
- deterministic exit codes;
- `--help` and preferably `doctor`;
- IDs, URLs, cursors, cache refs, or other follow-up handles;
- scriptable pagination/filtering/sorting;
- clear read/write boundaries, with writes gated by explicit flags;
- actionable `error.next_action` on failure.

## Browser/CDP Boundary

Browser automation is optional and must be configured by the user. Do not expose a browser control server by default. If you build a browser adapter, require explicit startup, localhost-only binding, local authorization, capability scoping, and clear site Terms-of-Service risk documentation.

## License

MIT.
