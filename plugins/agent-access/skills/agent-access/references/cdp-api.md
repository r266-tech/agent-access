# Browser/CDP Fallback Reference

This reference is not the default path. Read it only after Agent Access routing decides that existing CLI/API/search/fetch paths cannot cover the task cleanly.

## Role

Browser/CDP fallback covers:

- unknown dynamic pages where schema discovery is needed;
- one-off UI interaction or visual inspection;
- media frame inspection;
- login interactions that are not yet represented by a CLI;
- site behavior research that should later become a CLI feature or a focused pattern note.

Do not let a useful browser workaround become permanent. If the flow becomes repeatable, promote it into a CLI or a focused reference.

## Public-Core Safety Boundary

The public core does not ship an always-on browser control service.

If you add a browser adapter, require:

- explicit user startup;
- localhost-only binding;
- local authorization token or equivalent access control;
- capability scoping for eval, click, file upload, screenshots, and navigation;
- clear Terms-of-Service and account-risk warnings;
- no stealth, evasion, or anti-detection defaults;
- no access to existing user tabs unless explicitly requested.

## Work Pattern

- Read structure first: URL, title, text, forms, links, media, embedded data.
- Prefer structured extraction over screenshots.
- Use clicks only when the site requires real interaction.
- Preserve query parameters and state-bearing links.
- When you discover stable endpoints, schemas, selectors, or request bodies, feed them back into a CLI or focused reference.

## Reflection

Before finishing a browser-backed task, decide:

- stable endpoint/schema/pagination -> CLI;
- stable browser-specific trap -> focused reference;
- one-off visual judgment -> no durable prompt bloat;
- existing CLI friction -> improve the CLI and rerun.
