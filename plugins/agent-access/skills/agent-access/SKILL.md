---
name: agent-access
license: MIT
github: https://github.com/r266-tech/agent-access
description:
  Agent Access is a thin access layer for agents: route websites, GUI software, local apps, APIs, and recurring online workflows to agent-native CLIs, structured retrieval, browser fallback, Computer Use, or explicit contribution drafts.
metadata:
  author: Agent Access contributors
  version: "0.1.0"
---

# Agent Access Skill

Agent Access is a thin router. It should expose capability surfaces without replacing the model's judgment.

## L0 Contract

1. Clarify the target: information, evidence, page state, local app action, or external action.
2. Discover capabilities first: local agent CLIs, registry entries, structured APIs, search/fetch tools, browser fallback, and Computer Use.
3. Prefer CLI/API paths for stable repeatable tasks.
4. Use browser/GUI automation for exploration and fallback, not as the permanent default.
5. Promote stable endpoints, schemas, file formats, and operation sequences into CLIs.
6. After using a CLI, reflect on friction. If a safe improvement is obvious, improve and re-run the realistic flow.
7. Keep contribution explicit. Local lessons and patches remain local until reviewed, scrubbed, and user-approved.
8. Keep auth/session local. Credentials must go to OS keychain or a user-approved secret store, never to prompts, logs, memory, public repos, or contribution drafts.

## Capability Discovery

```bash
command -v agent-access
agent-access list
agent-access info example
# If the bin is not on PATH, run this from the loaded skill directory:
node scripts/agent-access.mjs list
```

Read `references/tool-routing.md` when the hot route is unclear. Read `references/cli-generation.md` before creating or substantially upgrading a CLI. Read `references/auth-sessions.md` for login/session work. Read `references/contribution-flow.md` before preparing anything for upstream.

## CLI Evolution Loop

- Output stable JSON.
- Include diagnostic errors and next actions.
- Return IDs/URLs/cursors/cache refs for follow-up reads.
- Keep pagination and filtering scriptable.
- Make read/write boundaries explicit.
- Dogfood realistic agent flows before declaring a route ready.

## Browser Fallback

Only enter browser/CDP fallback after deciding CLI/API paths do not cover the task. Browser control must be explicitly configured by the user and should not start implicitly in the public core.

Before using browser fallback, read `references/cdp-api.md` and any relevant site-pattern package installed by the user.

## Source Discipline

- Prefer primary sources: official docs, original pages, source code, papers, or APIs.
- Search engines are discovery tools, not final proof.
- Tool behavior must be checked through docs, source, `--help`, or direct probes.

## References

| File | When To Read |
|------|--------------|
| `references/tool-routing.md` | Need the full routing ladder |
| `references/cli-generation.md` | Need to create or upgrade an agent CLI |
| `references/cli-registry.md` | Need registry/install/package guidance |
| `references/auth-sessions.md` | Need login/session guidance |
| `references/contribution-flow.md` | Need to prepare a reviewed contribution |
| `references/cdp-api.md` | Need browser fallback guidance |
