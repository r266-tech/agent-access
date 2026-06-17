# CLI Registry Reference

Agent Access core stays thin. It carries a registry so agents can discover, install, diagnose, update, and route to companion CLIs without hardcoding every site into the skill.

## Entry Shape

Each entry should declare:

- `name`, `aliases`, `kind`, `targets`;
- `command` and optional real `command_aliases`;
- `description` as an agent-facing capability boundary;
- `repository` or upstream issue/source pointer;
- `install` with dry-run-displayable commands or clearly manual setup instructions;
- `update` with dry-run-displayable commands when available;
- `doctor` command when implemented;
- `auth.methods`, `auth.planned_methods`, `auth.broker`, `auth.local_state_only`, and delegated `auth.commands`;
- `read_write`: `read-only`, `read-mostly`, `write-capable`, or `external-action`;
- `write_policy` when writes exist;
- `outputs`: JSON, ids, urls, cursors, cache refs, citations, etc.;
- `source_status`: public release/source maturity;
- `quality`: verification and dogfood state.

Planned methods are not executable recovery paths. Do not advertise them as active login methods until they are implemented and dogfooded.

## Install And Update Contract

A promoted route should be discoverable and verifiable:

```bash
agent-access list
agent-access info <name>
agent-access install <name>        # dry-run plan
agent-access install <name> --run  # execute only when intended
agent-access update <name>         # dry-run plan
agent-access update <name> --run
agent-access doctor <name> --run
```

Manual or source-pending entries are acceptable in the public registry when the capability contract is useful, but they must be labeled clearly. Do not pretend a standalone installer exists.

## Source Status

Use one of these values:

- `public-release`: standalone release assets or package installer exist.
- `public-source`: source repo exists and install command is documented.
- `contract-public-source-pending`: registry contract is public, but standalone source/package still needs publication.
- `local-private`: private overlay only; do not ship in the public registry.

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

## Swarm Upgrade Flow

Users can improve the ecosystem by submitting:

- CLI friction reports;
- CLI patches;
- registry install/update improvements;
- focused references for site/app traps;
- source-status upgrades when a CLI becomes installable.

All submissions must be explicit, scrubbed, reviewed, and maintainer-approved before merge. Agent Access must not gather passive telemetry.
