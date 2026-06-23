# dianping-cli

`dp` is Agent Access's read-only, agent-friendly Dianping CLI.

Design goals:

- JSON-first output, including errors.
- Stable exit codes for agent control flow.
- No cookie export command.
- No raw cookie values in stdout/stderr.
- Browser mode first, using the existing Edge CDP proxy when available.
- HTTP mode remains explicit and rate-limited for controlled fallback.

## Install

Run it through Agent Access immediately:

```bash
agent-access run dp -- --help
```

Create local PATH shims when desired:

```bash
agent-access install dp --run
```

`dianping` is an alias shim.

## Commands

```bash
dp doctor --pretty
dp cities --pretty
dp search "望那儿" --city xiamen --limit 5 --pretty
dp shop 123456 --pretty
dp shop 123456 --format text
dp reviews 123456 --pretty
```

Default search mode is `browser`, which uses `http://127.0.0.1:3456` and the
user's normal Edge session. This avoids copying Dianping cookies into terminal
logs.

Use HTTP mode only when you intentionally want cookie-file based access:

```bash
dp search "望那儿" --mode http --city xiamen --pretty
```

## Auth Boundary

The preferred auth path is Edge login plus browser mode.

For HTTP fallback, import only from stdin:

```bash
pbpaste | dp auth import --stdin
dp auth status --pretty
```

The cookie file defaults to:

```text
~/.agent-access/state/dianping-cli/cookies.json
```

The CLI writes it with `0600` permissions and never implements cookie export.

## JSON Contract

Success:

```json
{
  "ok": true,
  "tool": "dianping-cli",
  "schema_version": 1,
  "command": "search",
  "mode": "browser",
  "city_id": 15,
  "keyword": "望那儿",
  "count": 1,
  "items": [
    {
      "shop_id": "H5iV0HiWjNaEzEb4",
      "name": "望那儿海景餐酒吧·WANNA ROOF",
      "review_count": "8429",
      "avg_price": "133",
      "category": "创意菜",
      "area": "环岛路沿线"
    }
  ]
}
```

Error:

```json
{
  "ok": false,
  "tool": "dianping-cli",
  "schema_version": 1,
  "error": {
    "code": "cdp_unavailable",
    "message": "Edge CDP proxy is not reachable",
    "details": {}
  },
  "next_actions": []
}
```

Common exit codes:

- `0`: success
- `2`: bad input or missing required auth material
- `3`: login required
- `4`: verification required
- `5`: network/CDP unavailable
- `6`: parse/extraction failure or web review text unavailable
- `70`: unexpected internal error

## Notes

This implementation borrows only high-level observations from public Dianping
scraper projects: Dianping search URLs use `/search/keyword/{city_id}/0_{query}`,
and Xiamen's city id is `15`. It does not vendor third-party code.

## Extracted Fields

`search` items currently expose:

- `shop_id`
- `name`
- `url`
- `review_count`
- `avg_price`
- `category`
- `area`
- `text_sample`
- `confidence`

`shop` items currently expose:

- `shop_id`
- `name`
- `rating`
- `review_count`
- `avg_price`
- `category_area`
- `business_hours`
- `address`
- `nearby`
- `url`
- `page_url`
- `text_sample`

`reviews` items expose real review text only when Dianping renders it in the web
page:

- `author`
- `date`
- `rating`
- `body`
- `images`
- `text_sample`
- `confidence`

Important: `review_count` from `search` or `shop` is only an aggregate count.
It is not review content. If the web page keeps review bodies behind the app or
the review API returns `403`, `dp reviews` fails closed with `ok:false`, for
example:

```json
{
  "ok": false,
  "command": "reviews",
  "error": {
    "code": "review_api_forbidden",
    "message": "Dianping review text is not available from the web page; the page review API returned 403."
  },
  "next_actions": [
    "Do not treat review_count as review text.",
    "Use the Dianping app or another source if full review bodies are required."
  ]
}
```
