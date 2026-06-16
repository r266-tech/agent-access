# Tool Routing

Read this when the thin skill is not enough to choose the right capability surface.

## Routing Ladder

1. Use a registered companion CLI when it exists and covers the task.
2. Use a structured API, SDK, source document, feed, or fetch path when it is stable and sufficient.
3. Use search for discovery, then verify against primary sources.
4. Use browser/CDP fallback only for dynamic pages, session-bound pages, media/visual inspection, or schema discovery that cannot yet be represented by a CLI.
5. Use Computer Use only for local GUI software or system surfaces that do not expose a better API, CLI, or file format.
6. After the task, promote repeatable discoveries into a CLI or focused reference.

## Companion CLI Checks

```bash
node scripts/agent-access.mjs list
node scripts/agent-access.mjs info <name>
command -v <cli>
<cli> --help
```

## CLI Evolution Signals

Improve or create a CLI when:

- output is not stable JSON;
- errors lack a machine-readable next action;
- list results cannot be followed up by ID, URL, cursor, or cache ref;
- pagination/filtering/sorting require ad hoc browser work;
- read/write boundaries are unclear;
- the same multi-step flow recurs.

Do not force CLI coverage for one-off visual judgment, unknown UI exploration, captchas, upload widgets, or high-risk external writes.
