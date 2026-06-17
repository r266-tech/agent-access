# Agent Access

Agent Access is a Codex plugin and thin access layer for agents. It helps an agent discover and use the right capability surface for a website, API, local app, GUI workflow, or recurring online task.

The goal is to package agent-friendly CLIs for external websites, local software, and web workflows, then make them improve through real use. Agent Access should stay thin: it routes, documents, installs, updates, and captures reviewed lessons; companion CLIs do the site/app-specific work.

## Principles

- Keep the default skill small. Load references only when needed.
- Prefer agent-native CLIs and structured APIs before browser or GUI automation.
- Treat browser/CDP and Computer Use as exploration or fallback paths.
- Turn stable repeated workflows into CLIs.
- Keep auth/session handling explicit and local.
- Let CLI use improve the system: after a task, fix obvious CLI friction or record a focused reference.
- Accept swarm contributions through explicit, scrubbed drafts and maintainer review, never passive telemetry.
- Never upload usage experience, logs, screenshots, cookies, tokens, account identifiers, local paths, or browser/session material without explicit review and confirmation.

## Architecture

Agent Access has four layers:

1. Thin Codex plugin: skill, registry, references, install/update helper, contribution workflow.
2. Companion CLIs: separate command surfaces for sites and apps.
3. Local user state: credentials, cookies, browser sessions, API keys, local databases, caches, and private overlays. This stays on the user's machine.
4. Maintained upstream: reviewed registry changes, CLI releases, and references that are safe to publish.

Public registry entries may describe login methods and update commands. They must not include user credentials, cookies, tokens, account identifiers, local browser dumps, or private paths.

## Initial CLI Pack

The first public registry pack declares these routes:

| Route | Command | Status | Notes |
| --- | --- | --- | --- |
| WeChat / Weixin local data | `wechat-cli` | public release | Reads local WeChat data; no sending or UI control. |
| Polymarket | `pmkt` | contract public, standalone source pending | Public read-only market/event research. |
| Xiaoyuzhou FM | `xyz` | public source | Read-only subscriptions, episodes, transcripts, search, history. |
| Douban movie | `douban` | contract public, standalone source pending | Browser-session auth; writes are dry-run unless explicit apply. |
| Dianping | `dp` / `dianping` | contract public, standalone source pending | Browser/session or stdin cookie import; no cookie export. |
| Xiaohongshu / Rednote | `xhs` | contract public, standalone source pending | User-owned local session; mutating actions require explicit command and approval. |

`source_status` in `registry.json` is authoritative. A route can be useful before its standalone installer is published, but `agent-access install <name>` must not pretend an installer exists.

## Quick Start

```bash
node plugins/agent-access/skills/agent-access/scripts/agent-access.mjs list
node plugins/agent-access/skills/agent-access/scripts/agent-access.mjs info wechat-cli
node plugins/agent-access/skills/agent-access/scripts/agent-access.mjs install wechat-cli
node plugins/agent-access/skills/agent-access/scripts/agent-access.mjs doctor wechat-cli --run
node plugins/agent-access/skills/agent-access/scripts/agent-access.mjs audit-public .
```

`install` and `update` are dry-run by default. Add `--run` only when you want the declared command executed on the local machine.

## Install In Codex App

From a local checkout:

```bash
codex plugin marketplace add .
codex plugin add agent-access --marketplace agent-access
```

From GitHub:

```bash
codex plugin marketplace add r266-tech/agent-access --ref main
codex plugin add agent-access --marketplace agent-access
```

Upgrade the marketplace snapshot when maintainers publish new registry, skill, or reference changes:

```bash
codex plugin marketplace upgrade agent-access
codex plugin add agent-access --marketplace agent-access
```

Companion CLIs update through their own registry-declared update commands, for example:

```bash
agent-access update wechat-cli
agent-access update wechat-cli --run
```

Use `AGENT_ACCESS_REGISTRY` to point at your own registry file when wiring private or experimental companion CLIs.
The package also declares an `agent-access` bin for local development tools that install package bins.

## Companion CLI Contract

Recommended companion CLIs should provide:

- stable JSON stdout for machine use;
- deterministic exit codes;
- `--help` and preferably `doctor`;
- IDs, URLs, cursors, cache refs, or other follow-up handles;
- scriptable pagination/filtering/sorting;
- clear read/write boundaries, with writes gated by explicit flags;
- local-only auth/session handling;
- actionable `error.next_action` on failure.

## Browser/CDP Boundary

Browser automation is optional and must be configured by the user. Do not expose a browser control server by default. If you build a browser adapter, require explicit startup, localhost-only binding, local authorization, capability scoping, and clear site Terms-of-Service risk documentation.

## License

MIT.
