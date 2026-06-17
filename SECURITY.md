# Security Policy

## Supported Versions

Security fixes apply to the latest public release.

## Reporting A Vulnerability

Do not open public issues containing secrets, cookies, tokens, private URLs, screenshots with account data, or exploit details. Use GitHub private vulnerability reporting when available, or contact the maintainers through a private channel before sharing sensitive details.

## Data Handling

Agent Access must not collect passive telemetry by default. Contribution drafts are local until the user reviews, scrubs, and explicitly approves sharing.

Never include:

- cookies, tokens, API keys, passwords, verification codes, or QR payloads;
- phone numbers, emails, usernames, account labels, or user ids unless explicitly approved;
- raw HAR files, browser logs, screenshots, local database rows, or private page bodies;
- local absolute paths outside a minimal reproducible example.

## Browser Automation

The public core does not start a browser control server by default. Browser adapters must require explicit startup, local-only access, authorization, capability scoping, and clear site Terms-of-Service risk disclosure.
