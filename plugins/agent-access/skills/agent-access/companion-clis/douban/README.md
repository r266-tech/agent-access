# douban CLI

Agent-only Douban CLI for babata / Agent Access.

It uses the user's Edge CDP session as the auth/session boundary and never
exports or persists raw Douban cookies. Output is always a JSON envelope.

## Commands

```bash
douban doctor
douban auth status
douban auth login
douban mine
douban nowplaying --city shanghai --limit 10
douban recommend-nowplaying --city shanghai --limit 5
douban recommend-nowplaying --city shanghai --limit 5 --new-only
douban search "肖申克的救赎"
douban movie 1292052
douban rating "肖申克的救赎"
douban rating 1292052
douban status 1292052
douban mark 1292052 wish
douban mark "肖申克的救赎" wish
douban mark 1292052 collect --rating 5 --apply
douban rate 1292052 --rating 5 --apply
douban cities
```

Commands that accept a subject can take a numeric id, full subject URL, or movie
title query. Query inputs resolve via Douban search and include
`resolved_subject` in the JSON output.

`recommend-nowplaying` ranks nowplaying movies by Douban score and excludes
`collect`/看过 by default. Use `--new-only` for movies whose release/year starts
with the current year, or `--year 2026` to pin a specific release year.

Write actions are dry-run by default. `mark` and `rate` only write to Douban
when `--apply` is present.

`douban auth login` opens the Douban login page in the user's Edge CDP session
and keeps that tab open for QR/manual login. After the user finishes login, run
`douban auth status` or `agent-access auth status douban --run`.
