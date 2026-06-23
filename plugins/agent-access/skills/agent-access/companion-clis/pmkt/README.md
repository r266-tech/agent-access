# pmkt

Read-only Polymarket CLI for Babata agents.

`pmkt` is intentionally smaller than the official trading CLI and the broader
community MCP servers. It reads public Polymarket APIs, emits JSON, and never
asks for wallet credentials, private keys, API keys, approvals, or order
placement.

## Why CLI First

This is an occasional lookup surface, similar in spirit to the local Xiaohongshu
and Xiaoyuzhou CLIs. A CLI is easier for agents to compose with `jq`, scripts,
and one-off probes. MCP can be added later as a thin wrapper if Polymarket
becomes a frequent always-on tool.

## Researched Sources

Representative public projects were reviewed before this implementation:

- `Polymarket/polymarket-cli`: official Rust CLI. Useful command grouping and
  endpoint reference, but includes wallet setup, approvals, orders, and on-chain
  operations.
- `Polymarket/py-clob-client`: official Python CLOB client, now archived and
  marked as no longer maintained.
- `pab1it0/polymarket-mcp`: lightweight Gamma API MCP. Useful shape, but some
  orderbook/trade tools use non-current experimental Gamma paths.
- `caiovicentino/polymarket-mcp-server`: broad MCP with dashboard and trading.
  Too much private-key and autonomous-trading surface for a default reader.
- `stat-guy/polymarket`: read-only research skill around the official CLI.
  Useful gotchas and workflows.
- `runesleo/polymarket-toolkit`: read-only public API toolkit and skills.
  Useful address/Data API patterns.
- `mneves75/polymarket-analyzer`: TUI using Gamma, CLOB REST/WS, and Data API.
  Useful handling of missing orderbooks as normal state.

## Commands

```bash
pmkt search "bitcoin" --limit 5
pmkt events --active --order volume --descending --limit 10
pmkt event https://polymarket.com/event/fed-decision-in-october
pmkt markets --active --order volumeNum --limit 10
pmkt market will-bitcoin-reach-100k-in-june-2026
pmkt resolve <event-or-market-url-or-slug>
pmkt summary <event-or-market-url-or-slug>
pmkt summary <event-slug> --active-only
pmkt summary <event-slug> --rules --context

pmkt clob price <TOKEN_ID> --side BUY
pmkt clob book <TOKEN_ID> --depth 5
pmkt clob midpoint <TOKEN_ID>
pmkt clob spread <TOKEN_ID>
pmkt clob history <TOKEN_ID> --interval 1d --fidelity 60

pmkt data holders <CONDITION_ID> --limit 20
pmkt data trades <CONDITION_ID> --limit 50
pmkt data positions <WALLET> --limit 50

pmkt sources
```

List/search commands exclude closed markets by default. Use `--include-closed`
or `--closed` when you need historical markets. Search/list event responses
show up to five embedded markets by default; direct event/resolve lookups show
up to ten. Pass `--market-limit 0` for all embedded markets, or use
`pmkt market <slug>` for focused market detail.

For agent planning, prefer `pmkt summary <event-or-market>`. It resolves event
vs market automatically and returns compact, stable odds fields (`yes_price`,
`no_price`, `best_bid`, `best_ask`, `last_trade_price`, volume, active/closed
state) plus `max_yes_price_market` and `max_no_price_market` over active
markets. Event summaries include closed markets by default so agents can account
for resolved time windows; pass `--active-only` to return only unresolved
markets. Pass `--rules` only when resolution text is needed, and `--context`
only when Polymarket-generated event context is needed, because both fields can
be long.

All successful commands return:

```json
{
  "ok": true,
  "schema_version": "1",
  "source": "pmkt",
  "version": "0.1.0",
  "command": "search",
  "data": {}
}
```

Errors also return JSON and exit non-zero.

## Data Sources

- Gamma API: `https://gamma-api.polymarket.com`
- CLOB public REST: `https://clob.polymarket.com`
- Data API: `https://data-api.polymarket.com`

No authentication is used.

## Gotchas Baked In

- `outcomes`, `outcomePrices`, and `clobTokenIds` often arrive as JSON strings,
  not arrays. `pmkt` parses and aligns them into `outcomes[]`.
- `/event/<slug>` and `/market/<slug>` URLs are routed differently.
- Gamma ordering keys are not fully uniform. For markets, `volumeNum` works in
  current API responses; for events, `volume` is commonly useful.
- Missing CLOB orderbooks are a normal market state, not automatically a tool
  failure.
- Wallet/profile Data API reads are public data only. Do not treat wallet
  analysis as identity proof.

## Verify

```bash
agent-access run pmkt -- --help
agent-access run pmkt -- search bitcoin --limit 2
agent-access run pmkt -- clob midpoint <TOKEN_ID>
```
