# Agent Access

**A universal access layer for AI agents. Route websites, apps, APIs, and repeat workflows to agent-native CLIs first, then use browser or GUI fallback only when a CLI/API cannot cover the job.**

Agent Access is for Claude Code, Codex, Cursor, OpenClaw, Hermes, OpenAI agents, local agent runtimes, and any coding or research agent that needs reliable access to the outside world.

It also ships a Codex plugin package, but the project is not "a Codex plugin." The plugin is just one adapter for the same portable registry, references, and CLI contract.

If this helps your agent stop clicking through the same website over and over, please star the repo. Stars make the registry easier for other agents and maintainers to find.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Node >=20](https://img.shields.io/badge/node-%3E%3D20-339933.svg)](package.json)

## Why This Exists

Agents still waste too much context and time on brittle browser automation:

- click a dynamic website;
- rediscover the same hidden endpoint;
- parse unstable page text;
- lose login/session state;
- produce output that another agent cannot safely continue.

Agent Access turns repeat access into reusable capability:

1. Discover the best access surface for the target.
2. Prefer a companion CLI or structured API.
3. Use browser/CDP/Computer Use only for gaps.
4. Promote stable discoveries into CLI contracts, registry entries, or focused references.
5. Keep credentials, cookies, browser profiles, and private paths local.

## What You Get

- `agent-access` CLI for registry lookup, install/update plans, doctor checks, auth routing, public audits, and contribution drafts.
- A portable `registry.json` for companion CLIs such as WeChat, Polymarket, Xiaoyuzhou, Douban, Dianping, and Xiaohongshu/Rednote.
- A thin skill package that tells agents how to choose tools without stuffing every rule into the prompt.
- References for CLI generation, auth/session boundaries, browser fallback, and contribution review.
- A Codex plugin package under `plugins/agent-access`.

## Works With

| Agent / runtime | Status | How to use it |
| --- | --- | --- |
| Claude Code | Portable | Use the CLI, registry, and skill text/reference files from this repo. |
| OpenAI Codex | Packaged | Install the bundled Codex plugin or use the CLI directly. |
| Cursor | Portable | Point rules/agent instructions at the registry and CLI contract. |
| OpenClaw | Portable | Use Agent Access as the access registry and CLI convention layer. |
| Hermes / Babata-style agents | Portable | Use the same thin routing layer with local private overlays. |
| Custom agents | Portable | Call `agent-access list/info/doctor` and adopt the CLI contract. |

For agent-runtime integration details, see [AGENTS.md](AGENTS.md).

## Quick Start

Use directly from GitHub:

```bash
npx github:r266-tech/agent-access --help
npx github:r266-tech/agent-access list
npx github:r266-tech/agent-access info wechat-cli
npx github:r266-tech/agent-access doctor wechat-cli
```

Use from a checkout:

```bash
git clone https://github.com/r266-tech/agent-access.git
cd agent-access
npm link

agent-access list
agent-access info wechat-cli
agent-access install wechat-cli      # dry-run plan
agent-access doctor wechat-cli --run # executes the target doctor command
```

`install` and `update` are dry-run by default. Add `--run` only when you intend to change the local machine.

## Codex Plugin

Install from GitHub:

```bash
codex plugin marketplace add r266-tech/agent-access --ref main
codex plugin add agent-access --marketplace agent-access
```

Install from a local checkout:

```bash
codex plugin marketplace add .
codex plugin add agent-access --marketplace agent-access
```

Upgrade the plugin package:

```bash
codex plugin marketplace upgrade agent-access
codex plugin add agent-access --marketplace agent-access
```

Companion CLIs update through their own registry-declared commands:

```bash
agent-access update wechat-cli
agent-access update wechat-cli --run
```

## Initial Registry

| Target | Command | Status | Boundary |
| --- | --- | --- | --- |
| WeChat / Weixin / 微信 local data | `wechat-cli`, `wx-cli` | Public release | Read local WeChat data. No sending, no UI control. |
| Polymarket | `pmkt` | Public contract, standalone source pending | Read market, event, price, outcome, order-book, trade, and holder data. No wallet credentials. |
| Xiaoyuzhou FM / 小宇宙 | `xyz` | Public source | Read subscriptions, episodes, transcripts, search, and history. |
| Douban movie / 豆瓣电影 | `douban` | Public contract, standalone source pending | Browser-session reads. Mark/rate defaults to dry-run; explicit apply required. |
| Dianping / 大众点评 | `dp`, `dianping` | Public contract, standalone source pending | Read shops and reviews via browser/session or stdin cookie import. No cookie export. |
| Xiaohongshu / Rednote / 小红书 | `xhs` | Public contract, standalone source pending | User session stays local. Writes require explicit command and confirmation. |

`plugins/agent-access/skills/agent-access/registry.json` is the source of truth. `source_status` tells agents whether a route is installable today or only a public contract.

## Agent-Native CLI Contract

A companion CLI should provide:

- stable JSON stdout by default;
- deterministic exit codes;
- useful `--help` and ideally `doctor`;
- IDs, URLs, cursors, cache refs, or other follow-up handles;
- scriptable pagination, filters, sorting, and fields;
- clear read/write boundaries;
- explicit write flags or dry-run defaults;
- local auth/session storage;
- actionable `error.next_action` on failure.

This is the core idea: websites and apps become durable tools that agents can compose.

## Architecture

Agent Access has four layers:

1. Universal thin layer: registry, references, contribution flow, audit checks, and CLI helper.
2. Adapters: Codex plugin today; other agent packages can point at the same files and CLI.
3. Companion CLIs: target-specific tools for websites, apps, APIs, local databases, and workflows.
4. User-local state: credentials, cookies, browser sessions, API keys, caches, and private overlays.

Public registry entries may describe login methods, install commands, and update commands. They must never contain user credentials, cookies, tokens, account identifiers, browser dumps, HAR files, raw logs, or private local paths.

## Privacy And Safety

Agent Access does not collect passive telemetry and does not auto-upload usage experience.

Contribution drafts are local by default. Before anything becomes public, it must be explicitly reviewed, scrubbed, and submitted by the user or maintainer.

Run the public audit before publishing:

```bash
npm test
node plugins/agent-access/skills/agent-access/scripts/agent-access.mjs audit-public .
```

## Repository Search Keywords

AI agent access layer, agent-native CLI, AI browser automation alternative, agent tool router, CLI registry for agents, Claude Code tools, Codex plugin, Cursor agent tools, OpenClaw tools, Hermes agent tools, Computer Use fallback, CDP fallback, local-first agent tools, WeChat CLI, Polymarket CLI, Xiaoyuzhou CLI, Douban CLI, Dianping CLI, Xiaohongshu CLI, Rednote CLI.

## Contributing

Useful contributions:

- new companion CLI contracts;
- registry entries for agent-friendly tools;
- references for stable site/app patterns;
- privacy-preserving auth/session adapters;
- tests and audit probes;
- docs that help agents choose the right capability.

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

## License

MIT.
