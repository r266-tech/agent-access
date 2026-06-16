# Contribution Flow Reference

Agent Access can support reviewed swarm-style improvements, but it must not collect passive telemetry or upload local experience automatically.

## Local Draft First

```bash
agent-access contributions list
agent-access contributions new --type cli-friction --target example --summary "..."
agent-access contributions show <draft-id>
agent-access contributions scrub <draft-id>
agent-access contributions submit <draft-id>
```

`submit` must be fail-closed until a user reviews the final artifact and explicitly approves sharing.

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
- tests or dogfood proof when behavior changes.
