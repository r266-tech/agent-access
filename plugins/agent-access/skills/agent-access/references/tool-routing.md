# Tool Routing

Read this when the thin skill is not enough to choose the right capability surface.

## Routing Ladder

1. Use a registered companion CLI when it exists and covers the task.
2. Use a structured API, SDK, source document, feed, or fetch path when it is stable and sufficient.
3. Use search for discovery, then verify against primary sources.
4. Use browser/CDP fallback only for dynamic pages, session-bound pages, media/visual inspection, or schema discovery that cannot yet be represented by a CLI.
5. Use Computer Use only for local GUI software or system surfaces that do not expose a better API, CLI, or file format.
6. After the task, promote repeatable discoveries into a CLI or focused reference.

## Initial CLI Routes

| Target | Route | Boundary |
| --- | --- | --- |
| WeChat / Weixin local data | `wechat-cli` / `wx-cli` | Local data read-only; no sending or UI control; user local profile only. |
| Polymarket | `pmkt` | Public read-only market/event data; no wallet/trading credentials. |
| Xiaoyuzhou FM | `xyz` | Read-only podcast data; SMS token stays local. |
| Douban movie | `douban` | Browser-session reads; mark/rate dry-run by default and require explicit apply. |
| Dianping | `dp` / `dianping` | Browser/session or stdin cookie import; no cookie export. |
| Xiaohongshu / Rednote | `xhs` | User session local; mutating upstream commands require explicit approval. |

Check `agent-access info <name>` before assuming a CLI is installed. `source_status` distinguishes public release, public source, and contract-public-source-pending routes.

## Companion CLI Checks

```bash
agent-access list
agent-access info <name>
agent-access install <name>
agent-access update <name>
agent-access doctor <name> --run
command -v <cli>
<cli> --help
```

`install` and `update` are dry-run by default. Use `--run` only when the user intends to install or update local code.

## CLI Evolution Signals

Improve or create a CLI when:

- output is not stable JSON;
- errors lack a machine-readable next action;
- list results cannot be followed up by ID, URL, cursor, or cache ref;
- pagination/filtering/sorting require ad hoc browser work;
- read/write boundaries are unclear;
- the same multi-step flow recurs;
- login can be guided but the post-login data path is stable;
- agent had to guess how to continue from command output.

Do not force CLI coverage for one-off visual judgment, unknown UI exploration, captchas, upload widgets, or high-risk external writes. Put those lessons into a reference instead.
