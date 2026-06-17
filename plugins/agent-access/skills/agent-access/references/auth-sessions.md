# Auth And Session Reference

Read this for login, refresh, session reuse, QR/SMS/OAuth/password/API-key flows, or auth failure diagnostics.

## Goals

- First use should guide the user through login.
- Existing sessions should be reusable.
- Expiry and refresh should be detectable.
- Multi-account/profile use should be explicit.
- Credentials must stay local and out of prompts, logs, public repos, and contribution drafts.

## Broker Shape

```bash
agent-access auth status
agent-access auth status <name>
agent-access auth login <name> --method qr
agent-access auth login <name> --method sms --phone <phone>
agent-access auth login <name> --method password --account <account> --secret-stdin
agent-access auth refresh <name>
agent-access auth forget <name>
agent-access auth doctor <name>
```

Delegated login commands should be dry-run by default. Use `--run` only when the user intends to perform the login action.

## Credential Storage

Prefer:

1. OS keychain / platform credential manager;
2. encrypted local store;
3. non-sensitive config files;
4. env vars only as temporary overrides.

Do not store raw credentials, verification codes, auth headers, browser logs, screenshots, or private page bodies in docs, logs, public repos, or contribution drafts.

The public Agent Access core does not write secrets directly. Password/API-key login should be implemented by a target-specific adapter or a user-approved secret store. If no adapter is registered, the command must fail closed rather than logging or storing the secret.

## CLI Auth Error Contract

```json
{
  "ok": false,
  "error": {
    "code": "auth_required",
    "message": "Login required",
    "next_action": "agent-access auth login <name> --method qr"
  }
}
```

## Contribution Boundary

Share only redacted method metadata, generic selectors, error codes, or recovery commands. Never share account identifiers or raw session material without explicit user approval.
