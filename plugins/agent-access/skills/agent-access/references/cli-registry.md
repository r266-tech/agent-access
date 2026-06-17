# CLI Registry Reference

Agent Access core stays thin. It carries a registry so agents can discover, install, diagnose, and route to companion CLIs without hardcoding every site into the skill.

## Entry Shape

Each entry should declare:

- `name`, `aliases`, `kind`, `targets`;
- `command` and optional real `command_aliases`;
- `description` as an agent-facing capability boundary;
- `install` with executable or clearly manual setup instructions;
- `doctor` command when implemented;
- `auth.methods`, `auth.planned_methods`, `auth.broker`, and delegated `auth.commands`;
- `read_write`: `read-only`, `read-mostly`, `write-capable`, or `external-action`;
- `outputs`: JSON, ids, urls, cursors, cache refs, citations, etc.;
- `quality`: verification and dogfood state.

Planned methods are not executable recovery paths. Do not advertise them as active login methods until they are implemented and dogfooded.

## Install Contract

A promoted route should be installable and verifiable:

```bash
agent-access list
agent-access info <name>
agent-access install <name>
agent-access doctor <name> --run
```

Manual installation is acceptable for experimental entries, but then the entry should not be promoted as a recommended hot route.

## Quality Gate

Before promoting a CLI:

1. `--help` is useful to an agent.
2. Read commands emit stable JSON.
3. Error paths include actionable next steps.
4. List -> detail -> follow-up works by stable handles.
5. Pagination/filtering are scriptable.
6. Auth/session failure has a diagnostic path.
7. Write/external actions require explicit flags.
8. A realistic task has been dogfooded after installation.
