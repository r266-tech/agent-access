# Contributing

Agent Access accepts deliberate, reviewed contributions: CLI contract improvements, registry entries, focused references, docs, tests, and safe adapters.

Before contributing:

1. Run the public audit:

   ```bash
   node plugins/agent-access/skills/agent-access/scripts/agent-access.mjs audit-public .
   ```

2. Remove secrets and private identifiers.
3. Include source-grounded evidence and reproduction steps.
4. Keep the default skill thin. Put details in references.
5. For CLI changes, include realistic dogfood output or tests.

Do not submit raw run logs, screenshots, cookies, tokens, HAR files, personal browsing history, private company URLs, or local paths that reveal user identity.
