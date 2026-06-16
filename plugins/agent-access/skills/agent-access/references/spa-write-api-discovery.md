# SPA Write API Discovery

Read this only when a user has explicitly approved exploring a write action and no safer documented API or CLI exists.

## Safety Rules

- Prefer official APIs and documented SDKs.
- Keep dry-run as the default.
- Do not submit external writes without explicit user approval.
- Never persist or publish raw auth/session values.
- Capture only endpoint shape, field names, validation rules, and redacted failure modes.

## Discovery Checklist

1. Identify the user-visible action and expected durable result.
2. Inspect the network request shape in a browser session the user approved.
3. Record method, path pattern, required non-secret fields, response schema, and verification step.
4. Implement a CLI dry-run first.
5. Add an explicit apply flag for real writes.
6. Verify by re-reading the target state.

Keep site-specific write details in a private or reviewed pattern package unless they are safe, generic, and legally appropriate to publish.
