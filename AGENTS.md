# Agent Access For Agents

Agent Access is a universal thin access layer. Use it with Claude Code, Codex,
Cursor, OpenClaw, Hermes, or a custom agent runtime when a task needs websites,
apps, APIs, local software, login-bound pages, or repeat workflows.

## Runtime Contract

1. Prefer registered companion CLIs and structured APIs.
2. Use browser/CDP/GUI automation only when a CLI/API cannot cover the job.
3. Promote stable discoveries into a CLI, registry entry, or focused reference.
4. Keep credentials, cookies, browser profiles, tokens, account IDs, raw logs,
   HAR files, screenshots, and private paths out of public outputs.
5. Treat Codex plugin files as one adapter, not the project boundary.

## First Commands

```bash
agent-access list
agent-access info <target>
agent-access install <target>
agent-access doctor <target> --run
```

`install` and `update` are dry-run by default. Add `--run` only when the user
intends to modify the local machine.

If `agent-access` is not on PATH, run the helper directly:

```bash
node plugins/agent-access/skills/agent-access/scripts/agent-access.mjs list
```

## Key Files

- `plugins/agent-access/skills/agent-access/registry.json`: public companion CLI
  registry.
- `plugins/agent-access/skills/agent-access/SKILL.md`: thin routing skill.
- `plugins/agent-access/skills/agent-access/references/cli-generation.md`: how
  to turn repeat website/app workflows into agent-native CLIs.
- `plugins/agent-access/skills/agent-access/references/auth-sessions.md`: local
  auth/session boundaries.
- `plugins/agent-access/skills/agent-access/references/contribution-flow.md`:
  scrubbed contribution flow.

## Public Repo Guard

Before publishing, run:

```bash
npm test
node plugins/agent-access/skills/agent-access/scripts/agent-access.mjs audit-public .
```
