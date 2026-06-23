from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from . import __version__
from .client import (
    PolymarketClient,
    PolymarketError,
    clean_none,
    detect_url_kind,
    extract_slug,
    normalize_book,
    normalize_event,
    normalize_market,
    summarize_event,
    summarize_market,
    to_bool,
    to_float,
)

SCHEMA_VERSION = "1"
SOURCE = "pmkt"


def ok(command: str | None, data: Any, *, warnings: list[str] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE,
        "version": __version__,
        "command": command,
        "data": data,
    }
    if warnings:
        payload["warnings"] = warnings
    return payload


def err(command: str | None, error: PolymarketError | Exception) -> dict[str, Any]:
    if isinstance(error, PolymarketError):
        body = error.as_dict()
    else:
        body = {"code": "unexpected", "message": str(error)}
    return {
        "ok": False,
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE,
        "version": __version__,
        "command": command,
        "error": body,
    }


def emit(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def positive_int(value: str) -> int:
    try:
        out = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid integer: {value}") from exc
    if out < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return out


def add_common_list_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--limit", type=positive_int, default=20)
    parser.add_argument("--offset", type=positive_int, default=0)
    parser.add_argument("--order", default=None)
    parser.add_argument("--ascending", action="store_true", default=None)
    parser.add_argument("--descending", action="store_true", default=False)
    parser.add_argument("--active", action="store_true", default=None)
    parser.add_argument("--inactive", action="store_true", default=False)
    parser.add_argument("--closed", action="store_true", default=None)
    parser.add_argument("--include-closed", action="store_true", default=False)
    parser.add_argument("--tag-id", type=int, default=None)
    parser.add_argument("--tag-slug", default=None)
    parser.add_argument("--full", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pmkt",
        description="Read-only Polymarket CLI. JSON output only.",
    )
    p.add_argument("--timeout", type=float, default=float(os.getenv("PMKT_TIMEOUT", "20")))
    p.add_argument("--version", action="version", version=f"pmkt {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("search", help="search Polymarket events, markets, tags, and profiles")
    sp.add_argument("query")
    sp.add_argument("--limit", type=positive_int, default=10)
    sp.add_argument("--page", type=positive_int, default=1)
    sp.add_argument("--closed", action="store_true")
    sp.add_argument("--profiles", action="store_true")
    sp.add_argument("--tags", action="store_true")
    sp.add_argument("--market-limit", type=positive_int, default=5)
    sp.add_argument("--full", action="store_true")

    sp = sub.add_parser("events", help="list events")
    add_common_list_flags(sp)
    sp.add_argument("--related-tags", action="store_true")
    sp.add_argument("--market-limit", type=positive_int, default=5)

    sp = sub.add_parser("event", help="get event by id, slug, or URL")
    sp.add_argument("id_or_slug_or_url")
    sp.add_argument("--market-limit", type=positive_int, default=10)
    sp.add_argument("--full", action="store_true")

    sp = sub.add_parser("markets", help="list markets")
    add_common_list_flags(sp)
    sp.add_argument("--condition-id", action="append", default=None)
    sp.add_argument("--token-id", action="append", default=None)

    sp = sub.add_parser("market", help="get market by id, slug, or URL")
    sp.add_argument("id_or_slug_or_url")
    sp.add_argument("--full", action="store_true")

    sp = sub.add_parser("resolve", help="resolve a Polymarket URL or slug as event first, then market")
    sp.add_argument("value")
    sp.add_argument("--market-limit", type=positive_int, default=10)
    sp.add_argument("--full", action="store_true")

    sp = sub.add_parser("summary", help="compact research summary for an event or market")
    sp.add_argument("value")
    sp.add_argument("--active-only", action="store_true", help="omit closed markets for event summaries")
    sp.add_argument("--rules", action="store_true", help="include resolution rules/descriptions")
    sp.add_argument("--context", action="store_true", help="include Polymarket-generated event context")

    clob = sub.add_parser("clob", help="read CLOB prices and order books")
    clob_sub = clob.add_subparsers(dest="clob_cmd", required=True)

    sp = clob_sub.add_parser("price", help="best price for token and side")
    sp.add_argument("token_id")
    sp.add_argument("--side", choices=["BUY", "SELL", "buy", "sell"], default="BUY")

    sp = clob_sub.add_parser("book", help="order book for a token")
    sp.add_argument("token_id")
    sp.add_argument("--depth", type=positive_int, default=10)

    sp = clob_sub.add_parser("midpoint", help="midpoint price for a token")
    sp.add_argument("token_id")

    sp = clob_sub.add_parser("spread", help="spread for a token")
    sp.add_argument("token_id")

    sp = clob_sub.add_parser("history", help="price history for a token")
    sp.add_argument("token_id")
    sp.add_argument("--interval", default="1d", choices=["1h", "6h", "1d", "1w", "1m", "max"])
    sp.add_argument("--fidelity", type=positive_int, default=None)

    data = sub.add_parser("data", help="read public Data API information")
    data_sub = data.add_subparsers(dest="data_cmd", required=True)

    sp = data_sub.add_parser("holders", help="holders for a condition id")
    sp.add_argument("condition_id")
    sp.add_argument("--limit", type=positive_int, default=20)

    sp = data_sub.add_parser("trades", help="trades for a condition id")
    sp.add_argument("condition_id")
    sp.add_argument("--limit", type=positive_int, default=50)
    sp.add_argument("--offset", type=positive_int, default=0)

    sp = data_sub.add_parser("positions", help="public positions for a wallet")
    sp.add_argument("wallet")
    sp.add_argument("--limit", type=positive_int, default=50)
    sp.add_argument("--offset", type=positive_int, default=0)
    sp.add_argument("--redeemable", action="store_true", default=None)

    sub.add_parser("sources", help="summarize researched upstream tools and adopted boundary")
    return p


def list_params(args: argparse.Namespace, *, kind: str) -> dict[str, Any]:
    params: dict[str, Any] = {
        "limit": args.limit,
        "offset": args.offset,
        "order": args.order,
    }
    if args.ascending is not None:
        params["ascending"] = args.ascending
    if args.descending:
        params["ascending"] = False
    if args.active is not None:
        params["active"] = args.active
    if args.inactive:
        params["active"] = False
    if args.closed is not None:
        params["closed"] = args.closed
    elif not args.include_closed:
        params["closed"] = False
    if args.include_closed:
        params.pop("closed", None)
    if args.tag_id is not None:
        params["tag_id"] = args.tag_id
    if args.tag_slug is not None and kind == "events":
        params["tag_slug"] = args.tag_slug
    if getattr(args, "related_tags", False):
        params["related_tags"] = True
    if getattr(args, "condition_id", None):
        params["condition_ids"] = args.condition_id
    if getattr(args, "token_id", None):
        params["clob_token_ids"] = args.token_id
    return clean_none(params)


def run(args: argparse.Namespace) -> dict[str, Any]:
    c = PolymarketClient(timeout=args.timeout)

    if args.cmd == "search":
        data = c.search(
            args.query,
            limit_per_type=args.limit,
            page=args.page,
            events_status=None if args.closed else "active",
            keep_closed_markets=1 if args.closed else 0,
            search_profiles=args.profiles,
            search_tags=args.tags,
            optimized=True,
        )
        normalized = {
            "query": args.query,
            "events": [
                normalize_event(e, full=args.full, market_limit=args.market_limit)
                for e in data.get("events", [])
            ],
            "tags": data.get("tags") or [],
            "profiles": data.get("profiles") or [],
            "pagination": data.get("pagination") or {},
        }
        return ok("search", normalized)

    if args.cmd == "events":
        raw = c.list_events(**list_params(args, kind="events"))
        return ok(
            "events",
            {
                "count": len(raw),
                "events": [
                    normalize_event(e, full=args.full, market_limit=args.market_limit)
                    for e in raw
                ],
            },
        )

    if args.cmd == "event":
        value = args.id_or_slug_or_url
        slug = extract_slug(value)
        if slug.isdigit() and detect_url_kind(value) is None:
            raw = c.event_by_id(slug)
        else:
            raw = c.event_by_slug(slug)
        return ok("event", normalize_event(raw, full=args.full, market_limit=args.market_limit))

    if args.cmd == "markets":
        raw = c.list_markets(**list_params(args, kind="markets"))
        return ok("markets", {"count": len(raw), "markets": [normalize_market(m, full=args.full) for m in raw]})

    if args.cmd == "market":
        value = args.id_or_slug_or_url
        slug = extract_slug(value)
        if slug.isdigit() and detect_url_kind(value) is None:
            raw = c.market_by_id(slug)
        else:
            raw = c.market_by_slug(slug)
        return ok("market", normalize_market(raw, full=args.full))

    if args.cmd == "resolve":
        return ok("resolve", resolve(c, args.value, full=args.full, market_limit=args.market_limit))

    if args.cmd == "summary":
        return ok(
            "summary",
            summary(
                c,
                args.value,
                include_closed=not args.active_only,
                include_description=args.rules,
                include_context=args.context,
            ),
        )

    if args.cmd == "clob":
        return run_clob(c, args)

    if args.cmd == "data":
        return run_data(c, args)

    if args.cmd == "sources":
        return ok("sources", sources_summary())

    raise PolymarketError("usage_error", f"unknown command {args.cmd}")


def resolve(
    c: PolymarketClient,
    value: str,
    *,
    full: bool = False,
    market_limit: int | None = None,
) -> dict[str, Any]:
    slug = extract_slug(value)
    kind = detect_url_kind(value)
    if kind == "market":
        return {"kind": "market", "market": normalize_market(c.market_by_slug(slug), full=full)}
    if kind == "event":
        return {
            "kind": "event",
            "event": normalize_event(c.event_by_slug(slug), full=full, market_limit=market_limit),
        }
    try:
        return {
            "kind": "event",
            "event": normalize_event(c.event_by_slug(slug), full=full, market_limit=market_limit),
        }
    except PolymarketError as first_error:
        if first_error.status != 404:
            raise
    return {"kind": "market", "market": normalize_market(c.market_by_slug(slug), full=full)}


def summary(
    c: PolymarketClient,
    value: str,
    *,
    include_closed: bool = True,
    include_description: bool = False,
    include_context: bool = False,
) -> dict[str, Any]:
    slug = extract_slug(value)
    kind = detect_url_kind(value)
    if kind == "market":
        return summarize_market(c.market_by_slug(slug), include_description=include_description)
    if kind == "event":
        return summarize_event(
            c.event_by_slug(slug),
            include_closed=include_closed,
            include_description=include_description,
            include_context=include_context,
        )
    try:
        return summarize_event(
            c.event_by_slug(slug),
            include_closed=include_closed,
            include_description=include_description,
            include_context=include_context,
        )
    except PolymarketError as first_error:
        if first_error.status != 404:
            raise
    return summarize_market(c.market_by_slug(slug), include_description=include_description)


def run_clob(c: PolymarketClient, args: argparse.Namespace) -> dict[str, Any]:
    if args.clob_cmd == "price":
        data = c.clob_price(args.token_id, args.side)
        return ok("clob price", {"token_id": args.token_id, "side": args.side.upper(), "price": to_float(data.get("price"))})
    if args.clob_cmd == "book":
        data = c.clob_book(args.token_id)
        return ok("clob book", normalize_book(data, depth=args.depth))
    if args.clob_cmd == "midpoint":
        data = c.clob_midpoint(args.token_id)
        return ok("clob midpoint", {"token_id": args.token_id, "mid": to_float(data.get("mid"))})
    if args.clob_cmd == "spread":
        data = c.clob_spread(args.token_id)
        return ok("clob spread", {"token_id": args.token_id, "spread": to_float(data.get("spread"))})
    if args.clob_cmd == "history":
        data = c.clob_history(args.token_id, interval=args.interval, fidelity=args.fidelity)
        return ok("clob history", {"token_id": args.token_id, "interval": args.interval, "history": data.get("history") or []})
    raise PolymarketError("usage_error", f"unknown clob command {args.clob_cmd}")


def run_data(c: PolymarketClient, args: argparse.Namespace) -> dict[str, Any]:
    if args.data_cmd == "holders":
        data = c.data_holders(args.condition_id, limit=args.limit)
        return ok("data holders", data)
    if args.data_cmd == "trades":
        data = c.data_trades(args.condition_id, limit=args.limit, offset=args.offset)
        return ok("data trades", data)
    if args.data_cmd == "positions":
        params: dict[str, Any] = {"limit": args.limit, "offset": args.offset}
        if args.redeemable is not None:
            params["redeemable"] = to_bool(args.redeemable)
        data = c.data_positions(args.wallet, **params)
        return ok("data positions", data)
    raise PolymarketError("usage_error", f"unknown data command {args.data_cmd}")


def sources_summary() -> dict[str, Any]:
    return {
        "decision": "Ship a Babata-owned read-only CLI first. Do not register an MCP server until the query surface needs always-on tool discovery.",
        "adopted": [
            {
                "source": "Polymarket/polymarket-cli",
                "used_for": "command grouping and official endpoint coverage reference",
                "not_adopted": "wallet setup, approve, order placement, and chain operations",
            },
            {
                "source": "stat-guy/polymarket",
                "used_for": "research workflow gotchas: outcomePrices/clobTokenIds can be JSON strings; URL kind matters; Gamma order keys are picky",
                "not_adopted": "Claude skill orchestration and shell-injected prefetch",
            },
            {
                "source": "runesleo/polymarket-toolkit",
                "used_for": "read-only public API boundary and wallet/profile Data API patterns",
                "not_adopted": "Node 22 TypeScript runtime dependency and broader profile/PnL skills",
            },
            {
                "source": "pab1it0/polymarket-mcp",
                "used_for": "minimal Gamma-only MCP shape",
                "not_adopted": "non-current experimental Gamma orderbook/trades endpoints",
            },
            {
                "source": "mneves75/polymarket-analyzer",
                "used_for": "missing orderbooks are normal; CLOB REST/WS split",
                "not_adopted": "Bun TUI and WebSocket dashboard",
            },
            {
                "source": "Polymarket/py-clob-client",
                "used_for": "historical CLOB method names only",
                "not_adopted": "runtime dependency because the repository is archived and points users to a newer SDK",
            },
        ],
        "runtime_boundary": {
            "readonly": True,
            "requires_api_key": False,
            "requires_wallet_or_private_key": False,
            "writes_or_trades": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        emit(run(args))
        return 0
    except BrokenPipeError:
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except Exception:
            pass
        return 0
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        command = None
        try:
            command = parser.parse_known_args(argv)[0].cmd
        except Exception:
            command = None
        emit(err(command, exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
