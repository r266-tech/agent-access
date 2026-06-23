from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
DATA_BASE = "https://data-api.polymarket.com"
APP_BASE = "https://polymarket.com"

USER_AGENT = "pmkt/0.1 (+https://polymarket.com; readonly)"
DEFAULT_TIMEOUT = 20.0

URL_SLUG_RE = re.compile(r"polymarket\.com/(?:event|market)/([^/?#]+)", re.I)


class PolymarketError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int | None = None,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.status is not None:
            out["status"] = self.status
        if self.details is not None:
            out["details"] = self.details
        return out


def extract_slug(value: str) -> str:
    match = URL_SLUG_RE.search(value)
    if match:
        return match.group(1).strip()
    cleaned = value.strip().split("?", 1)[0].split("#", 1)[0].rstrip("/")
    if "/" in cleaned:
        cleaned = cleaned.rsplit("/", 1)[-1]
    if not cleaned:
        raise PolymarketError("usage_error", "empty slug or URL")
    return cleaned


def detect_url_kind(value: str) -> str | None:
    lowered = value.lower()
    if "polymarket.com/event/" in lowered:
        return "event"
    if "polymarket.com/market/" in lowered:
        return "market"
    return None


def parse_jsonish(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default


def to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y"}:
            return True
        if lowered in {"0", "false", "no", "n"}:
            return False
    return bool(value)


def clean_none(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: clean_none(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [clean_none(v) for v in obj]
    return obj


def _outcomes(market: dict[str, Any]) -> list[str]:
    outcomes = parse_jsonish(market.get("outcomes"), [])
    if not isinstance(outcomes, list):
        return []
    return [str(x) for x in outcomes]


def _prices(market: dict[str, Any]) -> list[float | None]:
    prices = parse_jsonish(market.get("outcomePrices"), [])
    if not isinstance(prices, list):
        return []
    return [to_float(x) for x in prices]


def _token_ids(market: dict[str, Any]) -> list[str]:
    token_ids = (
        market.get("clobTokenIds")
        or market.get("clob_token_ids")
        or market.get("tokenIds")
        or market.get("token_ids")
    )
    parsed = parse_jsonish(token_ids, [])
    if isinstance(parsed, list):
        return [str(x) for x in parsed if x is not None]
    tokens = market.get("tokens")
    if isinstance(tokens, list):
        out = []
        for token in tokens:
            if isinstance(token, dict):
                token_id = token.get("token_id") or token.get("tokenID") or token.get("id")
                if token_id is not None:
                    out.append(str(token_id))
        return out
    return []


def normalize_market(market: dict[str, Any], *, full: bool = False) -> dict[str, Any]:
    outcomes = _outcomes(market)
    prices = _prices(market)
    token_ids = _token_ids(market)
    outcome_rows = []
    for i, outcome in enumerate(outcomes):
        outcome_rows.append(
            clean_none(
                {
                    "outcome": outcome,
                    "price": prices[i] if i < len(prices) else None,
                    "token_id": token_ids[i] if i < len(token_ids) else None,
                }
            )
        )

    events = market.get("events") if isinstance(market.get("events"), list) else []
    parent_event = events[0] if events and isinstance(events[0], dict) else {}

    out = {
        "id": str(market.get("id") or ""),
        "slug": market.get("slug"),
        "url": f"{APP_BASE}/market/{market.get('slug')}" if market.get("slug") else None,
        "question": market.get("question") or market.get("title"),
        "group_item_title": market.get("groupItemTitle"),
        "condition_id": market.get("conditionId") or market.get("condition_id"),
        "question_id": market.get("questionID") or market.get("question_id"),
        "active": market.get("active"),
        "closed": market.get("closed"),
        "accepting_orders": market.get("acceptingOrders"),
        "enable_order_book": market.get("enableOrderBook"),
        "end_date": market.get("endDate") or market.get("end_date"),
        "start_date": market.get("startDate") or market.get("start_date"),
        "liquidity": to_float(market.get("liquidityNum") or market.get("liquidity")),
        "volume": to_float(market.get("volumeNum") or market.get("volume")),
        "volume_24h": to_float(market.get("volume24hr") or market.get("volume24h")),
        "volume_1w": to_float(market.get("volume1wk")),
        "volume_1mo": to_float(market.get("volume1mo")),
        "best_bid": to_float(market.get("bestBid") or market.get("best_bid")),
        "best_ask": to_float(market.get("bestAsk") or market.get("best_ask")),
        "spread": to_float(market.get("spread")),
        "last_trade_price": to_float(market.get("lastTradePrice")),
        "outcomes": outcome_rows,
        "event": clean_none(
            {
                "id": str(parent_event.get("id")) if parent_event.get("id") is not None else None,
                "slug": parent_event.get("slug"),
                "title": parent_event.get("title"),
                "url": f"{APP_BASE}/event/{parent_event.get('slug')}" if parent_event.get("slug") else None,
            }
        ),
    }
    if full:
        out["description"] = market.get("description")
        out["resolution_source"] = market.get("resolutionSource")
        out["raw"] = market
    return clean_none(out)


def normalize_event(
    event: dict[str, Any],
    *,
    full: bool = False,
    market_limit: int | None = None,
) -> dict[str, Any]:
    markets = event.get("markets") if isinstance(event.get("markets"), list) else []
    visible_markets = markets if not market_limit else markets[:market_limit]
    truncated = len(markets) - len(visible_markets)
    out = {
        "id": str(event.get("id") or ""),
        "ticker": event.get("ticker"),
        "slug": event.get("slug"),
        "url": f"{APP_BASE}/event/{event.get('slug')}" if event.get("slug") else None,
        "title": event.get("title"),
        "active": event.get("active"),
        "closed": event.get("closed"),
        "archived": event.get("archived"),
        "featured": event.get("featured"),
        "restricted": event.get("restricted"),
        "end_date": event.get("endDate") or event.get("end_date"),
        "start_date": event.get("startDate") or event.get("start_date"),
        "liquidity": to_float(event.get("liquidity")),
        "volume": to_float(event.get("volume")),
        "volume_24h": to_float(event.get("volume24hr") or event.get("volume24h")),
        "volume_1w": to_float(event.get("volume1wk")),
        "open_interest": to_float(event.get("openInterest")),
        "comment_count": event.get("commentCount"),
        "market_count": len(markets),
        "markets": [normalize_market(m, full=full) for m in visible_markets if isinstance(m, dict)],
        "markets_truncated": truncated if truncated > 0 else None,
    }
    if full:
        out["description"] = event.get("description")
        out["resolution_source"] = event.get("resolutionSource")
        out["raw"] = event
    return clean_none(out)


def outcome_price(market: dict[str, Any], outcome_name: str) -> float | None:
    wanted = outcome_name.strip().lower()
    for row in _market_outcome_rows(market):
        if row["outcome"].strip().lower() == wanted:
            return row["price"]
    return None


def market_summary_row(market: dict[str, Any], *, include_description: bool = False) -> dict[str, Any]:
    row = normalize_market(market, full=False)
    out: dict[str, Any] = {
        "id": row.get("id"),
        "slug": row.get("slug"),
        "url": row.get("url"),
        "question": row.get("question"),
        "group_item_title": row.get("group_item_title"),
        "active": row.get("active"),
        "closed": row.get("closed"),
        "accepting_orders": row.get("accepting_orders"),
        "end_date": row.get("end_date"),
        "volume": row.get("volume"),
        "volume_24h": row.get("volume_24h"),
        "liquidity": row.get("liquidity"),
        "best_bid": row.get("best_bid"),
        "best_ask": row.get("best_ask"),
        "spread": row.get("spread"),
        "last_trade_price": row.get("last_trade_price"),
        "yes_price": outcome_price(market, "Yes"),
        "no_price": outcome_price(market, "No"),
        "outcomes": _market_outcome_rows(market),
    }
    if include_description:
        out["description"] = market.get("description")
        out["resolution_source"] = market.get("resolutionSource")
    return clean_none(out)


def summarize_market(market: dict[str, Any], *, include_description: bool = False) -> dict[str, Any]:
    row = market_summary_row(market, include_description=include_description)
    events = market.get("events") if isinstance(market.get("events"), list) else []
    event = events[0] if events and isinstance(events[0], dict) else {}
    return clean_none(
        {
            "kind": "market",
            "market": row,
            "event": {
                "id": str(event.get("id")) if event.get("id") is not None else None,
                "slug": event.get("slug"),
                "title": event.get("title"),
                "url": f"{APP_BASE}/event/{event.get('slug')}" if event.get("slug") else None,
            },
        }
    )


def summarize_event(
    event: dict[str, Any],
    *,
    include_closed: bool = True,
    include_description: bool = False,
    include_context: bool = False,
) -> dict[str, Any]:
    markets = [m for m in event.get("markets", []) if isinstance(m, dict)]
    rows = [market_summary_row(m, include_description=False) for m in markets]
    active_rows_all = [m for m in rows if m.get("active") and not m.get("closed")]
    closed_rows_all = [m for m in rows if m.get("closed")]
    if not include_closed:
        rows = [m for m in rows if not m.get("closed")]
    max_yes_price_market = _max_market_by_price(active_rows_all, "yes_price")
    max_no_price_market = _max_market_by_price(active_rows_all, "no_price")
    out: dict[str, Any] = {
        "kind": "event",
        "id": str(event.get("id") or ""),
        "ticker": event.get("ticker"),
        "slug": event.get("slug"),
        "url": f"{APP_BASE}/event/{event.get('slug')}" if event.get("slug") else None,
        "title": event.get("title"),
        "active": event.get("active"),
        "closed": event.get("closed"),
        "end_date": event.get("endDate") or event.get("end_date"),
        "start_date": event.get("startDate") or event.get("start_date"),
        "volume": to_float(event.get("volume")),
        "volume_24h": to_float(event.get("volume24hr") or event.get("volume24h")),
        "liquidity": to_float(event.get("liquidity")),
        "open_interest": to_float(event.get("openInterest")),
        "market_count": len(markets),
        "returned_market_count": len(rows),
        "active_market_count": len(active_rows_all),
        "closed_market_count": len(closed_rows_all),
        "max_yes_price_market": max_yes_price_market,
        "max_no_price_market": max_no_price_market,
        "markets": rows,
    }
    metadata = event.get("eventMetadata")
    if isinstance(metadata, dict) and include_context:
        out["context_updated_at"] = metadata.get("context_updated_at")
        out["context_description"] = metadata.get("context_description")
    if include_description:
        out["description"] = event.get("description")
        out["resolution_source"] = event.get("resolutionSource")
        out["market_resolution_rules"] = _first_market_description(markets)
    return clean_none(out)


def _market_outcome_rows(market: dict[str, Any]) -> list[dict[str, Any]]:
    outcomes = _outcomes(market)
    prices = _prices(market)
    rows = []
    for i, outcome in enumerate(outcomes):
        rows.append({"outcome": outcome, "price": prices[i] if i < len(prices) else None})
    return rows


def _max_market_by_price(markets: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    priced = [m for m in markets if isinstance(m.get(key), (int, float))]
    if not priced:
        return None
    best = max(priced, key=lambda row: row[key])
    return clean_none(
        {
            "market_slug": best.get("slug"),
            "question": best.get("question"),
            "group_item_title": best.get("group_item_title"),
            "url": best.get("url"),
            key: best.get(key),
            "best_bid": best.get("best_bid"),
            "best_ask": best.get("best_ask"),
            "last_trade_price": best.get("last_trade_price"),
            "volume": best.get("volume"),
        }
    )


def _first_market_description(markets: list[dict[str, Any]]) -> str | None:
    for market in markets:
        description = market.get("description")
        if isinstance(description, str) and description.strip():
            return description
    return None


def normalize_book(book: dict[str, Any], *, depth: int | None = None) -> dict[str, Any]:
    bids = _order_rows(book.get("bids"), reverse=True)
    asks = _order_rows(book.get("asks"), reverse=False)
    if depth is not None and depth >= 0:
        bids = bids[:depth]
        asks = asks[:depth]
    return clean_none(
        {
            "market": book.get("market"),
            "asset_id": str(book.get("asset_id") or ""),
            "timestamp": book.get("timestamp"),
            "bids": bids,
            "asks": asks,
            "best_bid": bids[0] if bids else None,
            "best_ask": asks[0] if asks else None,
            "min_order_size": to_float(book.get("min_order_size")),
            "tick_size": to_float(book.get("tick_size")),
            "neg_risk": book.get("neg_risk"),
            "last_trade_price": to_float(book.get("last_trade_price")),
        }
    )


def _order_rows(value: Any, *, reverse: bool) -> list[dict[str, Any]]:
    rows = []
    if not isinstance(value, list):
        return rows
    for item in value:
        if not isinstance(item, dict):
            continue
        price = to_float(item.get("price"))
        size = to_float(item.get("size"))
        if price is None or size is None:
            continue
        rows.append({"price": price, "size": size})
    return sorted(rows, key=lambda row: row["price"], reverse=reverse)


@dataclass
class PolymarketClient:
    timeout: float = DEFAULT_TIMEOUT
    gamma_base: str = GAMMA_BASE
    clob_base: str = CLOB_BASE
    data_base: str = DATA_BASE

    def get_json(
        self,
        base: str,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        method: str = "GET",
        body: Any | None = None,
    ) -> Any:
        url = self._build_url(base, path, params)
        data = None
        headers = {
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            details = _read_error_body(exc)
            raise PolymarketError(
                "http_error",
                f"{path} returned HTTP {exc.code}",
                status=exc.code,
                details=details,
            ) from exc
        except urllib.error.URLError as exc:
            raise PolymarketError("network_error", str(exc.reason)) from exc
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise PolymarketError("invalid_json", f"{path} returned invalid JSON") from exc

    @staticmethod
    def _build_url(base: str, path: str, params: dict[str, Any] | None) -> str:
        url = f"{base.rstrip('/')}/{path.lstrip('/')}"
        query = encode_params(params or {})
        return f"{url}?{query}" if query else url

    def list_events(self, **params: Any) -> list[dict[str, Any]]:
        data = self.get_json(self.gamma_base, "/events", params)
        if not isinstance(data, list):
            raise PolymarketError("shape_error", "Gamma /events did not return a list", details=data)
        return data

    def list_markets(self, **params: Any) -> list[dict[str, Any]]:
        data = self.get_json(self.gamma_base, "/markets", params)
        if not isinstance(data, list):
            raise PolymarketError("shape_error", "Gamma /markets did not return a list", details=data)
        return data

    def event_by_slug(self, slug: str) -> dict[str, Any]:
        data = self.get_json(self.gamma_base, f"/events/slug/{urllib.parse.quote(slug)}", None)
        if not isinstance(data, dict):
            raise PolymarketError("shape_error", "Gamma event lookup did not return an object", details=data)
        return data

    def market_by_slug(self, slug: str) -> dict[str, Any]:
        data = self.get_json(self.gamma_base, f"/markets/slug/{urllib.parse.quote(slug)}", None)
        if not isinstance(data, dict):
            raise PolymarketError("shape_error", "Gamma market lookup did not return an object", details=data)
        return data

    def event_by_id(self, event_id: str) -> dict[str, Any]:
        data = self.get_json(self.gamma_base, f"/events/{urllib.parse.quote(event_id)}", None)
        if not isinstance(data, dict):
            raise PolymarketError("shape_error", "Gamma event lookup did not return an object", details=data)
        return data

    def market_by_id(self, market_id: str) -> dict[str, Any]:
        data = self.get_json(self.gamma_base, f"/markets/{urllib.parse.quote(market_id)}", None)
        if not isinstance(data, dict):
            raise PolymarketError("shape_error", "Gamma market lookup did not return an object", details=data)
        return data

    def search(self, query: str, **params: Any) -> dict[str, Any]:
        merged = {"q": query, **params}
        data = self.get_json(self.gamma_base, "/public-search", merged)
        if not isinstance(data, dict):
            raise PolymarketError("shape_error", "Gamma search did not return an object", details=data)
        return data

    def clob_price(self, token_id: str, side: str) -> dict[str, Any]:
        data = self.get_json(self.clob_base, "/price", {"token_id": token_id, "side": side.upper()})
        if not isinstance(data, dict):
            raise PolymarketError("shape_error", "CLOB price did not return an object", details=data)
        return data

    def clob_book(self, token_id: str) -> dict[str, Any]:
        data = self.get_json(self.clob_base, "/book", {"token_id": token_id})
        if not isinstance(data, dict):
            raise PolymarketError("shape_error", "CLOB book did not return an object", details=data)
        return data

    def clob_midpoint(self, token_id: str) -> dict[str, Any]:
        data = self.get_json(self.clob_base, "/midpoint", {"token_id": token_id})
        if not isinstance(data, dict):
            raise PolymarketError("shape_error", "CLOB midpoint did not return an object", details=data)
        return data

    def clob_spread(self, token_id: str) -> dict[str, Any]:
        data = self.get_json(self.clob_base, "/spread", {"token_id": token_id})
        if not isinstance(data, dict):
            raise PolymarketError("shape_error", "CLOB spread did not return an object", details=data)
        return data

    def clob_history(
        self,
        token_id: str,
        *,
        interval: str = "1d",
        fidelity: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"market": token_id, "interval": interval}
        if fidelity is not None:
            params["fidelity"] = fidelity
        data = self.get_json(self.clob_base, "/prices-history", params)
        if not isinstance(data, dict):
            raise PolymarketError("shape_error", "CLOB history did not return an object", details=data)
        return data

    def data_holders(self, condition_id: str, **params: Any) -> Any:
        return self.get_json(self.data_base, "/holders", {"market": condition_id, **params})

    def data_trades(self, condition_id: str, **params: Any) -> Any:
        return self.get_json(self.data_base, "/trades", {"market": condition_id, **params})

    def data_positions(self, user: str, **params: Any) -> Any:
        return self.get_json(self.data_base, "/positions", {"user": user, **params})


def _read_error_body(exc: urllib.error.HTTPError) -> Any:
    try:
        raw = exc.read().decode("utf-8")
    except Exception:
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw[:500]


def encode_params(params: dict[str, Any]) -> str:
    pairs: list[tuple[str, str]] = []
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            pairs.append((key, "true" if value else "false"))
        elif isinstance(value, (list, tuple)):
            for item in value:
                if item is not None:
                    pairs.append((key, str(item)))
        else:
            pairs.append((key, str(value)))
    return urllib.parse.urlencode(pairs)
