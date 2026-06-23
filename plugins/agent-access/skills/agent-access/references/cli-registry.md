# CLI Registry Reference

Agent Access core stays thin. It carries a registry so agents can discover, install, diagnose, update, and route to companion CLIs without hardcoding every site into the skill.

`cli-manifest.json` is a deterministic discovery index generated from `registry.json`. It is not a separate source of truth. The package gate must fail when the manifest is stale or when an entry disappears without reviewed intent.

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
- `source_strategy`, `source_contract`, and `source_note`;
- `verify`: required flow, fixture policy, evidence, and residual risk;
- `quality`: verification, dogfood state, and safe `probes[]`;
- `error_contract`: exit codes, JSON error envelope, next action, and no sentinel rows.

Planned methods are not executable recovery paths. Do not advertise them as active login methods until they are implemented and dogfooded.

## Install And Update Contract

A promoted route should be discoverable and verifiable:

```bash
agent-access list
agent-access info <name>
agent-access run <name> -- --help   # immediate path for bundled CLIs
agent-access install <name>        # dry-run plan
agent-access install <name> --run  # execute only when intended
agent-access update <name>         # dry-run plan
agent-access update <name> --run
agent-access doctor <name> --run
```

Manual or source-pending entries are acceptable in the public registry when the capability contract is useful, but they must be labeled clearly. Do not pretend a standalone installer exists.

`agent-access list/info` exposes `install.state`:

- `installable`: registry declares executable install commands and a doctor command.
- `installable` with `install.bundled: true`: the companion CLI ships inside the plugin and can run through `agent-access run <name> -- ...` before any PATH shim is installed.
- `contract-only`: the public capability contract exists, but the standalone companion CLI installer is still pending.
- `manual-or-unknown`: the entry is incomplete for public promotion and should not be advertised as user-installable.

The release gate enforces this boundary. `public-release` and `public-source` entries must include `install.commands` or `install.type: bundled`, plus `doctor`; bundled entries must point to files under `companion-clis/`; `contract-public-source-pending` entries must keep `install.type: source-pending` and must not declare fake install commands.

## Manifest Gate

Use the manifest gate before packaging:

```bash
agent-access check-manifest
agent-access build-manifest --write
```

`build-manifest` is dry-run by default. If the generated manifest differs from the committed one, it reports the drift and exits non-zero until rerun with `--write`. It reads the packaged `registry.json` by default and deliberately ignores `AGENT_ACCESS_REGISTRY`; use `--registry FILE --output FILE` only for temporary local checks. If an existing or git-baseline manifest entry would be removed, the command fails unless the reviewer explicitly passes `--allow-removals`.

Do not edit `cli-manifest.json` by hand. Edit `registry.json`, run `build-manifest --write`, then review the diff.

## Overlay Shadow Audit

Users may keep private registry overlays outside the public package. Agent Access does not auto-merge or upload them. Use:

```bash
agent-access audit-overlay
AGENT_ACCESS_REGISTRY=/path/to/private-registry.json agent-access audit-overlay --strict
agent-access audit-overlay --registry /path/to/private-registry.json --strict
```

The audit reports local-only entries and entries that shadow packaged routes by name, command, alias, or target. Local overlay entry names are redacted by default; add `--reveal-local` only during a user-approved local diagnostic. `--strict` makes packaged-route shadowing fail so release and support flows can stop before an agent trusts the wrong route contract.

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

## Verify Contract

`verify.required_flow` uses short labels such as `help`, `doctor`,
`auth-status`, `list`, `search`, `detail`, `follow-up`,
`pagination`, `filter`, `error-path`, `dry-run`, `apply`, and
`read-back`.

`fixture_policy` is one of `redacted-fixture`, `live-probe`, or
`manual-only`. Registry `quality.probes[]` must only contain safe commands;
private account probes belong in local state, not in the public package.

## Swarm Upgrade Flow

Users can improve the ecosystem by submitting:

- CLI friction reports;
- CLI patches;
- registry install/update improvements;
- focused references for site/app traps;
- source-status upgrades when a CLI becomes installable.

All submissions must be explicit, scrubbed, reviewed, and maintainer-approved before merge. Agent Access must not gather passive telemetry.
