# Contribution Flow Reference

Agent Access can support reviewed swarm-style improvements, but it must not collect passive telemetry or upload local experience automatically.

## Local Draft First

```bash
agent-access contributions list
agent-access contributions new --type cli-friction --target xhs --summary "..."
agent-access contributions show <draft-id>
agent-access contributions scrub <draft-id>
agent-access contributions submit <draft-id>
```

`submit` must be fail-closed until a user reviews the final artifact and explicitly approves sharing.
`scrub` is a helper, not a proof. If residual privacy patterns remain, it must report `needs_manual_review` and refuse to mark the draft clean.

## What Belongs Upstream

Good upstream material:

- generic CLI command shape and output schema improvements;
- install/update fixes that do not include local paths or credentials;
- selector/API/schema notes that do not expose account data;
- reference notes about browser/CDP traps, redacted failure modes, and recovery commands;
- tests and dogfood evidence with private values replaced.

Keep local:

- cookies, tokens, API keys, passwords, QR payloads, SMS codes;
- account identifiers, usernames, phone numbers, emails, avatars;
- local filesystem paths, local DB rows, browser logs, HAR files, screenshots;
- private/company workflows, non-public endpoints, and personal site-pattern packs.

## Redaction Rules

Remove or replace:

- credentials and auth/session material;
- verification codes and QR payloads;
- phone numbers, emails, usernames, account labels, user ids;
- private URLs with state or account identifiers;
- local absolute paths outside a minimal repro;
- logged-in page bodies, browser logs, HAR files, screenshots, local DB rows.

## Review Gate

Contributions should include:

- clear target and scope;
- source-grounded evidence;
- reproduction steps;
- maintained agent-native CLI contract;
- tests or dogfood proof when behavior changes;
- maintainer decision before merge/release.

The maintainer decides what enters the public plugin or companion CLI release. Swarm users can propose improvements; they cannot silently change the shared package.
