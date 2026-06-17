# CLI Error Contract

Read this when building, reviewing, or promoting a companion CLI.

## Exit Codes

Use 2 for bad arguments, 66 for valid empty results, 1 for command/upstream
failure, 69 for unavailable local service, 75 for timeout, 77 for auth
required, 78 for config error, and 130 for interruption.

## Error Envelope

```json
{
  "ok": false,
  "error": {
    "code": "AUTH_REQUIRED",
    "message": "Login required",
    "next_action": "agent-access auth login TARGET --method browser-session"
  }
}
```

## Registry Requirements

Routes should declare `error_contract.exit_codes`,
`json_error_envelope: true`, `next_action: true`, and
`no_sentinel_rows: true`.
