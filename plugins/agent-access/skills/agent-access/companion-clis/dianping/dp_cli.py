#!/usr/bin/env python3
"""Agent-friendly Dianping CLI for babata.

The CLI is read-only by default and returns machine-readable JSON envelopes.
It intentionally never prints raw cookies.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import html
import json
import os
import re
import socket
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


APP_NAME = "dianping-cli"
SCHEMA_VERSION = 1
DEFAULT_CITY_ID = int(os.environ.get("DP_CITY_ID", "15"))
DEFAULT_CDP_BASE = os.environ.get("DP_CDP_BASE", "http://127.0.0.1:3456")
DEFAULT_TIMEOUT = float(os.environ.get("DP_TIMEOUT", "15"))
DEFAULT_WORKSPACE = Path(os.environ.get("BABATA_WORKSPACE", Path.home() / ".agent-access"))
DEFAULT_STATE_DIR = Path(os.environ.get("DP_STATE_DIR", DEFAULT_WORKSPACE / "state" / "dianping-cli"))
DEFAULT_COOKIE_FILE = Path(os.environ.get("DP_COOKIE_FILE", DEFAULT_STATE_DIR / "cookies.json"))
DEFAULT_CACHE_DIR = Path(os.environ.get("DP_CACHE_DIR", DEFAULT_STATE_DIR / "cache"))
DEFAULT_RATE_LIMIT_SECONDS = float(os.environ.get("DP_RATE_LIMIT_SECONDS", "2.0"))
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"
)

CITY_ALIASES = {
    "beijing": 2,
    "bj": 2,
    "shanghai": 1,
    "sh": 1,
    "guangzhou": 4,
    "gz": 4,
    "shenzhen": 7,
    "sz": 7,
    "hangzhou": 3,
    "hz": 3,
    "chengdu": 8,
    "cd": 8,
    "xiamen": 15,
    "xm": 15,
    "quanzhou": 134,
    "qz": 134,
}


class AgentError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        exit_code: int = 1,
        details: dict[str, Any] | None = None,
        next_actions: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code
        self.details = details or {}
        self.next_actions = next_actions or []


@dataclasses.dataclass
class HttpResult:
    url: str
    status: int
    final_url: str
    body: str
    headers: dict[str, str]


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def strip_tags(value: str) -> str:
    return compact_text(re.sub(r"<[^>]+>", " ", value or ""))


def parse_city(value: str | int | None) -> int:
    if value is None:
        return DEFAULT_CITY_ID
    if isinstance(value, int):
        return value
    lowered = value.strip().lower()
    if lowered.isdigit():
        return int(lowered)
    if lowered in CITY_ALIASES:
        return CITY_ALIASES[lowered]
    raise AgentError(
        "unknown_city",
        f"Unknown city {value!r}",
        exit_code=2,
        details={"known_aliases": sorted(CITY_ALIASES)},
        next_actions=["Use a numeric Dianping city_id or run `dp cities`."],
    )


def mkdir_private(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except PermissionError:
        pass


def atomic_write_text(path: Path, text: str, mode: int = 0o600) -> None:
    mkdir_private(path.parent)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent), text=True)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def read_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        raise AgentError(
            "invalid_json_file",
            "Invalid JSON in a local state file",
            exit_code=2,
            details={"file": "local_state_file", "error": str(exc)},
        ) from exc


def file_mode(path: Path) -> str | None:
    try:
        return oct(stat.S_IMODE(path.stat().st_mode))
    except FileNotFoundError:
        return None


def same_path(left: Path, right: Path) -> bool:
    try:
        return left.expanduser().resolve(strict=False) == right.expanduser().resolve(strict=False)
    except RuntimeError:
        return str(left) == str(right)


def path_source(path: Path, default_path: Path, env_name: str) -> str:
    if same_path(path, default_path):
        return f"env:{env_name}" if os.environ.get(env_name) else "default"
    return "custom"


def local_file_status(path: Path, default_path: Path, env_name: str) -> dict[str, Any]:
    return {
        "source": path_source(path, default_path, env_name),
        "exists": path.exists(),
        "mode": file_mode(path),
    }


def parse_cookie_header(raw: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for part in raw.replace("\n", ";").split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            pairs[key] = value
    return pairs


def normalize_cookie_payload(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        if "cookies" in raw and isinstance(raw["cookies"], dict):
            raw = raw["cookies"]
        return {str(k): str(v) for k, v in raw.items() if isinstance(v, (str, int, float))}
    if isinstance(raw, list):
        result: dict[str, str] = {}
        for item in raw:
            if isinstance(item, dict) and item.get("name") and item.get("value"):
                result[str(item["name"])] = str(item["value"])
        return result
    return {}


def load_cookie_header(cookie_file: Path) -> tuple[str | None, dict[str, Any]]:
    raw = read_json_file(cookie_file)
    cookies = normalize_cookie_payload(raw)
    selected = {k: v for k, v in cookies.items() if k in {"dper", "dplet", "_lxsdk_cuid", "_lxsdk"}}
    status = {
        **local_file_status(cookie_file, DEFAULT_COOKIE_FILE, "DP_COOKIE_FILE"),
        "has_dper": bool(cookies.get("dper")),
        "has_dplet": bool(cookies.get("dplet")),
        "stored_keys": sorted(k for k in cookies if k in {"dper", "dplet", "_lxsdk_cuid", "_lxsdk"}),
    }
    if not selected:
        return None, status
    header = "; ".join(f"{k}={v}" for k, v in selected.items())
    return header, status


class Cache:
    def __init__(self, directory: Path, enabled: bool = True) -> None:
        self.directory = directory
        self.enabled = enabled

    def key_path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.json"

    def get(self, key: str, max_age_seconds: int) -> dict[str, Any] | None:
        if not self.enabled or max_age_seconds <= 0:
            return None
        path = self.key_path(key)
        raw = read_json_file(path)
        if not isinstance(raw, dict):
            return None
        created = raw.get("cached_at_epoch")
        if not isinstance(created, (int, float)):
            return None
        if time.time() - float(created) > max_age_seconds:
            return None
        payload = raw.get("payload")
        return payload if isinstance(payload, dict) else None

    def set(self, key: str, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        data = {
            "cached_at": now_iso(),
            "cached_at_epoch": time.time(),
            "payload": payload,
        }
        atomic_write_text(self.key_path(key), json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def rate_limit(state_dir: Path, min_interval: float) -> None:
    if min_interval <= 0:
        return
    mkdir_private(state_dir)
    path = state_dir / "rate-limit.json"
    raw = read_json_file(path)
    last = raw.get("last_request_epoch") if isinstance(raw, dict) else None
    if isinstance(last, (int, float)):
        delay = min_interval - (time.time() - float(last))
        if delay > 0:
            time.sleep(delay)
    atomic_write_text(path, json.dumps({"last_request_epoch": time.time(), "updated_at": now_iso()}) + "\n")


def http_get(url: str, *, cookie_file: Path, timeout: float, state_dir: Path, min_interval: float) -> tuple[HttpResult, dict[str, Any]]:
    rate_limit(state_dir, min_interval)
    cookie_header, cookie_status = load_cookie_header(cookie_file)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
        "Referer": "https://www.dianping.com/",
    }
    if cookie_header:
        headers["Cookie"] = cookie_header
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")
            return (
                HttpResult(
                    url=url,
                    status=response.status,
                    final_url=response.geturl(),
                    body=body,
                    headers={k.lower(): v for k, v in response.headers.items()},
                ),
                cookie_status,
            )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return (
            HttpResult(
                url=url,
                status=exc.code,
                final_url=exc.geturl(),
                body=body,
                headers={k.lower(): v for k, v in exc.headers.items()},
            ),
            cookie_status,
        )
    except urllib.error.URLError as exc:
        raise AgentError(
            "network_error",
            "Dianping HTTP request failed",
            exit_code=5,
            details={"url": url, "reason": str(exc.reason)},
            next_actions=["Retry later or use `--mode browser` with Edge logged in."],
        ) from exc


def detect_gate(text: str, final_url: str = "") -> dict[str, Any]:
    sample = text[:2000]
    login = bool(re.search(r"login|account\.dianping|登录|请登录", final_url + "\n" + sample, re.I))
    verify = bool(re.search(r"验证|验证码|verify|captcha|risk|安全校验", final_url + "\n" + sample, re.I))
    blocked = bool(re.search(r"禁止访问|访问过于频繁|403|机器人", sample, re.I))
    return {"login": login, "verify": verify, "blocked": blocked}


class ShopAnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.current: dict[str, Any] | None = None
        self.anchors: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {k.lower(): v or "" for k, v in attrs}
        href = attrs_dict.get("href", "")
        if tag.lower() == "a" and "/shop/" in href:
            self.current = {"href": href, "text": []}
            self.depth = 1
        elif self.current is not None:
            self.depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self.current is None:
            return
        self.depth -= 1
        if self.depth <= 0:
            text = compact_text(" ".join(self.current["text"]))
            href = str(self.current["href"])
            if text:
                self.anchors.append({"href": href, "text": text})
            self.current = None

    def handle_data(self, data: str) -> None:
        if self.current is not None and data.strip():
            self.current["text"].append(data)


def absolute_dianping_url(href: str) -> str:
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return "https://www.dianping.com" + href
    return href


def shop_id_from_url(url: str) -> str | None:
    match = re.search(r"/shop/([A-Za-z0-9]+)", url)
    return match.group(1) if match else None


def parse_search_html(body: str, *, limit: int) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    parser = ShopAnchorParser()
    try:
        parser.feed(body)
    except Exception as exc:  # HTMLParser should be forgiving; keep evidence if it is not.
        warnings.append(f"html_parser_error:{type(exc).__name__}")

    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for anchor in parser.anchors:
        url = absolute_dianping_url(anchor["href"])
        shop_id = shop_id_from_url(url)
        if not shop_id or shop_id in seen:
            continue
        seen.add(shop_id)
        name = anchor["text"]
        if len(name) > 80:
            name = name[:80].rstrip() + "..."
        items.append(
            {
                "shop_id": shop_id,
                "name": name,
                "url": url.split("?")[0],
                "confidence": "anchor_text",
            }
        )
        if len(items) >= limit:
            break

    if not items:
        for match in re.finditer(r'href=["\']([^"\']*/shop/([A-Za-z0-9]+)[^"\']*)["\'][^>]*>([\s\S]{0,600}?)</a>', body):
            url = absolute_dianping_url(match.group(1))
            shop_id = match.group(2)
            if shop_id in seen:
                continue
            name = strip_tags(match.group(3))
            if not name:
                continue
            seen.add(shop_id)
            items.append({"shop_id": shop_id, "name": name[:80], "url": url.split("?")[0], "confidence": "regex_fallback"})
            if len(items) >= limit:
                break

    if not items:
        warnings.append("no_shop_items_parsed")
    return items, warnings


def extract_json_ld(body: str) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>',
        re.I,
    )
    for match in pattern.finditer(body):
        raw = html.unescape(match.group(1)).strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            docs.append(parsed)
        elif isinstance(parsed, list):
            docs.extend(item for item in parsed if isinstance(item, dict))
    return docs


def regex_field(body: str, *patterns: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, body, re.I)
        if match:
            value = compact_text(match.group(1))
            if value:
                return value
    return None


def parse_shop_html(body: str, *, shop_id: str) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    json_ld = extract_json_ld(body)
    merged: dict[str, Any] = {}
    for doc in json_ld:
        for key in ("name", "address", "telephone", "priceRange", "aggregateRating"):
            if key in doc and key not in merged:
                merged[key] = doc[key]

    title = regex_field(body, r"<title[^>]*>(.*?)</title>")
    name = (
        compact_text(str(merged.get("name", "")))
        or regex_field(body, r'"shopName"\s*:\s*"([^"]+)"', r'"name"\s*:\s*"([^"]+)"')
        or (title.split("-")[0].strip() if title else None)
    )
    address = merged.get("address")
    if isinstance(address, dict):
        address = " ".join(str(address.get(k, "")) for k in ("streetAddress", "addressLocality", "addressRegion"))
    address_text = compact_text(str(address or "")) or regex_field(body, r'"address"\s*:\s*"([^"]+)"')
    phone = compact_text(str(merged.get("telephone", ""))) or regex_field(body, r'"phoneNo"\s*:\s*"([^"]+)"')
    avg_price = regex_field(body, r'"avgPrice"\s*:\s*"?([^",}]+)"?', r"人均\s*[￥¥]?\s*(\d+)")
    rating = regex_field(body, r'"scoreText"\s*:\s*"([^"]+)"', r'"ratingValue"\s*:\s*"?([^",}]+)"?')

    if not name:
        warnings.append("shop_name_not_found")
    return (
        {
            "shop_id": shop_id,
            "name": name,
            "address": address_text or None,
            "phone": phone or None,
            "avg_price": avg_price,
            "rating": rating,
            "url": f"https://www.dianping.com/shop/{shop_id}",
            "json_ld_count": len(json_ld),
        },
        warnings,
    )


class CdpProxy:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, path: str, *, data: str | bytes | None = None) -> Any:
        url = self.base_url + path
        body: bytes | None
        if data is None:
            body = None
        elif isinstance(data, bytes):
            body = data
        else:
            body = data.encode("utf-8")
        request = urllib.request.Request(url, data=body)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                text = response.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            raise AgentError(
                "cdp_unavailable",
                "Edge CDP proxy is not reachable",
                exit_code=5,
                details={"base_url": self.base_url, "reason": str(getattr(exc, "reason", exc))},
                next_actions=[
                    "Run web-access check-deps or use `dp search --mode http` if you intentionally want cookie-based HTTP.",
                    "Make sure Edge is running with the babata CDP LaunchAgent.",
                ],
            ) from exc
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise AgentError(
                "cdp_bad_response",
                "CDP proxy returned non-JSON response",
                exit_code=5,
                details={"base_url": self.base_url, "sample": text[:300]},
            ) from exc

    def ping(self) -> bool:
        try:
            self._request("/targets")
            return True
        except AgentError:
            return False

    def new(self, url: str) -> str:
        encoded = urllib.parse.urlencode({"url": url})
        data = self._request(f"/new?{encoded}")
        target = data.get("targetId") if isinstance(data, dict) else None
        if not target:
            raise AgentError("cdp_new_failed", "Failed to create browser tab", exit_code=5, details={"response": data})
        return str(target)

    def close(self, target_id: str) -> None:
        try:
            self._request(f"/close?target={urllib.parse.quote(target_id)}")
        except AgentError:
            pass

    def eval_json(self, target_id: str, script: str) -> Any:
        data = self._request(f"/eval?target={urllib.parse.quote(target_id)}", data=script)
        value = data.get("value") if isinstance(data, dict) else data
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value


BROWSER_SEARCH_JS = r"""
(() => {
  const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
  const abs = (href) => {
    try { return new URL(href, location.href).href; } catch { return href || ""; }
  };
  const idFrom = (href) => {
    const m = (href || "").match(/\/shop\/([A-Za-z0-9]+)/);
    return m ? m[1] : "";
  };
  const parseCard = (sample) => {
    const review = sample.match(/([0-9万+]+)\s*条评价/);
    const price = sample.match(/人均\s*[¥￥]\s*([0-9]+)/);
    const categoryArea = sample.match(/人均\s*[¥￥]\s*[0-9]+\s+([^|]+?)\s*\|\s*([^|]+)/);
    return {
      review_count: review ? review[1] : null,
      avg_price: price ? price[1] : null,
      category: categoryArea ? clean(categoryArea[1]) : null,
      area: categoryArea ? clean(categoryArea[2]) : null
    };
  };
  const text = document.body ? document.body.innerText || "" : "";
  const anchors = Array.from(document.querySelectorAll('a[href*="/shop/"]'));
  const seen = new Set();
  const items = [];
  for (const a of anchors) {
    const href = abs(a.getAttribute("href"));
    const shopId = idFrom(href);
    if (!shopId || seen.has(shopId)) continue;
    seen.add(shopId);
    const card = a.closest("li, [class*=shop], [class*=card], [class*=item]") || a;
    const titleEl = card.querySelector("h4, h3, h2, [class*=shop-name], [class*=title], [class*=tit]") || a;
    const sample = clean(card.innerText).slice(0, 300);
    const parsed = parseCard(sample);
    items.push({
      shop_id: shopId,
      name: clean(titleEl.innerText || a.innerText).slice(0, 100),
      url: href.split("?")[0],
      review_count: parsed.review_count,
      avg_price: parsed.avg_price,
      category: parsed.category,
      area: parsed.area,
      text_sample: sample,
      confidence: "browser_dom"
    });
  }
  return JSON.stringify({
    page_title: document.title,
    page_url: location.href,
    item_count: items.length,
    items,
    gate: {
      login: /登录|请登录|account\.dianping/.test(text + location.href),
      verify: /验证|验证码|verify|captcha|安全校验/.test(text + location.href),
      blocked: /禁止访问|访问过于频繁|机器人/.test(text)
    },
    text_sample: clean(text).slice(0, 600)
  });
})()
"""


BROWSER_SHOP_JS = r"""
(() => {
  const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
  const text = document.body ? document.body.innerText || "" : "";
  const pageTitleName = (document.title.match(/【([^】]+)】/) || [])[1] || "";
  const domTitle = clean(document.querySelector("h1, [class*=shop-name], [class*=title]")?.innerText || "");
  const title = clean(pageTitleName || domTitle || document.title);
  const fullText = clean(text);
  const pick = (re) => {
    const m = fullText.match(re);
    return m ? clean(m[1] || m[0]) : null;
  };
  const addressMatch = fullText.match(/(?:^| )([^ ]{2,120}(?:路|街|道|巷|里|号|楼|层)[^ ]{0,80}?)(?: 距| 到店| 代金券| 团购| 推荐菜| 菜单|$)/);
  const scripts = Array.from(document.querySelectorAll('script[type*="ld+json"]')).map(s => s.textContent || "");
  let jsonLd = [];
  for (const raw of scripts) {
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) jsonLd.push(...parsed);
      else if (parsed && typeof parsed === "object") jsonLd.push(parsed);
    } catch {}
  }
  return JSON.stringify({
    page_title: document.title,
    page_url: location.href,
    title,
    rating: pick(/★ ★ ★ ★ ★ ([0-9.]+)/),
    review_count: pick(/([0-9万+]+)条[¥￥]/),
    avg_price: pick(/[¥￥]([0-9]+)\/人/),
    category_area: pick(/[¥￥][0-9]+\/人 ([^ ]+?) 口味[:：]/),
    business_hours: pick(/(营业中[^ ]+)/),
    address: addressMatch ? clean(addressMatch[1]) : null,
    nearby: pick(/距([^ ]+?[0-9.]+(?:m|km))/),
    json_ld: jsonLd.slice(0, 3),
    gate: {
      login: /登录|请登录|account\.dianping/.test(text + location.href),
      verify: /验证|验证码|verify|captcha|安全校验/.test(text + location.href),
      blocked: /禁止访问|访问过于频繁|机器人/.test(text)
    },
    text_sample: clean(text).slice(0, 1200)
  });
})()
"""


BROWSER_REVIEWS_JS = r"""
(async () => {
  const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
  const text = document.body ? document.body.innerText || "" : "";
  const fullText = clean(text);
  const gate = {
    login: /登录|请登录|account\.dianping/.test(text + location.href),
    verify: /验证|验证码|verify|captcha|安全校验/.test(text + location.href),
    blocked: /禁止访问|访问过于频繁|机器人/.test(text)
  };
  const reviewRoot = document.querySelector("#review-list-new-pc, [class*=review-list], [class*=comment-list]");
  const appRequired = /移步至大众点评App|打开大众点评App|去大众点评App查看|App查看|扫码/.test(text);
  const datePattern = /(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?|\d{1,2}[-/.月]\d{1,2}日?|今天|昨天|前天|\d+\s*(?:分钟前|小时前|天前|周前|月前))/;
  const ratingPattern = /(?:评分|打分|星级|综合)[^\d]{0,8}([1-5](?:\.\d)?)|([1-5](?:\.\d)?)\s*分/;
  const selectors = [
    "#review-list-new-pc li",
    "#review-list-new-pc [class*=review]",
    "#review-list-new-pc [class*=comment]",
    "[class*=review-item]",
    "[class*=reviewItem]",
    "[class*=comment-item]",
    "[class*=commentItem]",
    "[class*=review-card]",
    "[class*=comment-card]"
  ].join(",");
  const candidates = Array.from(document.querySelectorAll(selectors));
  const seen = new Set();
  const items = [];
  const isBadSample = (sample) => {
    if (!sample || sample.length < 20) return true;
    if (/移步至大众点评App|打开大众点评App|没有下载大众点评App|推荐菜|菜单\(|团购套餐|抢购/.test(sample)) return true;
    return false;
  };
  for (const el of candidates) {
    const sample = clean(el.innerText || "");
    if (isBadSample(sample)) continue;
    const bodyEl = el.querySelector("[class*=review-words], [class*=comment-content], [class*=content], [class*=desc], p") || el;
    let body = clean(bodyEl.innerText || sample);
    if (isBadSample(body)) body = sample;
    const key = body.slice(0, 180);
    if (seen.has(key)) continue;
    seen.add(key);
    const authorEl = el.querySelector("[class*=user], [class*=name], [class*=nick], a[href*='member']");
    const date = (sample.match(datePattern) || [null])[0];
    const ratingMatch = sample.match(ratingPattern);
    const rating = ratingMatch ? (ratingMatch[1] || ratingMatch[2] || null) : null;
    const images = Array.from(el.querySelectorAll("img"))
      .map(img => img.currentSrc || img.src || img.getAttribute("data-src") || "")
      .filter(src => /^https?:\/\//.test(src))
      .slice(0, 12);
    items.push({
      author: authorEl ? clean(authorEl.innerText || authorEl.textContent || "") || null : null,
      date: date || null,
      rating,
      body: body.slice(0, 2000),
      images,
      text_sample: sample.slice(0, 800),
      confidence: "browser_dom"
    });
  }

  const resources = performance.getEntriesByType("resource").map(e => e.name);
  const reviewApiUrl = resources.find(u => /mapi\/review\/outsideshopreviewlist\.bin/i.test(u)) || null;
  let apiProbe = null;
  if (reviewApiUrl) {
    try {
      const res = await fetch(reviewApiUrl, { credentials: "include", cache: "no-store" });
      const contentType = res.headers.get("content-type") || "";
      const buf = await res.arrayBuffer();
      let decoded = "";
      try { decoded = new TextDecoder("utf-8").decode(buf); } catch {}
      apiProbe = {
        url: reviewApiUrl,
        status: res.status,
        status_text: res.statusText,
        content_type: contentType,
        byte_length: buf.byteLength,
        text_sample: clean(decoded).slice(0, 500)
      };
    } catch (e) {
      apiProbe = { url: reviewApiUrl, error: String(e) };
    }
  }
  return JSON.stringify({
    page_title: document.title,
    page_url: location.href,
    gate,
    app_required: appRequired,
    review_root: reviewRoot ? {
      id: reviewRoot.id || "",
      class_name: typeof reviewRoot.className === "string" ? reviewRoot.className : "",
      text_length: clean(reviewRoot.innerText || "").length,
      html_length: (reviewRoot.innerHTML || "").length
    } : null,
    review_api_url: reviewApiUrl,
    api_probe: apiProbe,
    resource_hits: resources.filter(u => /review|comment|mapi/i.test(u)).slice(0, 20),
    items,
    item_count: items.length,
    text_sample: fullText.slice(0, 1200)
  });
})()
"""


def search_url(keyword: str, city_id: int) -> str:
    return "https://www.dianping.com/search/keyword/%d/0_%s" % (city_id, urllib.parse.quote(keyword, safe=""))


def shop_url(shop_id: str) -> str:
    return f"https://www.dianping.com/shop/{urllib.parse.quote(shop_id, safe='')}"


def review_item_from_text(text: str, *, confidence: str = "html_regex") -> dict[str, Any] | None:
    sample = compact_text(text)
    if len(sample) < 20:
        return None
    if re.search(r"移步至大众点评App|打开大众点评App|推荐菜|菜单\(|团购套餐|抢购", sample):
        return None
    date = regex_field(
        sample,
        r"(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)",
        r"(\d{1,2}[-/.月]\d{1,2}日?)",
        r"(今天|昨天|前天|\d+\s*(?:分钟前|小时前|天前|周前|月前))",
    )
    rating = regex_field(
        sample,
        r"(?:评分|打分|星级|综合)[^\d]{0,8}([1-5](?:\.\d)?)",
        r"([1-5](?:\.\d)?)\s*分",
    )
    return {
        "author": None,
        "date": date,
        "rating": rating,
        "body": sample[:2000],
        "images": [],
        "text_sample": sample[:800],
        "confidence": confidence,
    }


def parse_reviews_html(body: str, *, limit: int) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    block_pattern = re.compile(
        r"<(?:div|li|section|article)\b[^>]*(?:class|id)=['\"][^'\"]*(?:review|comment)[^'\"]*['\"][^>]*>([\s\S]{20,4000}?)</(?:div|li|section|article)>",
        re.I,
    )
    for match in block_pattern.finditer(body):
        block = match.group(0)
        text = strip_tags(block)
        item = review_item_from_text(text)
        if not item:
            continue
        images = re.findall(r"<img\b[^>]+(?:src|data-src)=['\"]([^'\"]+)['\"]", block, re.I)
        item["images"] = [absolute_dianping_url(src) for src in images if src][:12]
        key = item["body"][:180]
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
        if len(items) >= limit:
            break
    if not items:
        warnings.append("no_review_items_parsed")
    return items, warnings


def base_payload(command: str, **extra: Any) -> dict[str, Any]:
    payload = {
        "ok": True,
        "tool": APP_NAME,
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "generated_at": now_iso(),
    }
    payload.update(extra)
    return payload


def with_gate_warnings(payload: dict[str, Any], gate: dict[str, Any]) -> dict[str, Any]:
    warnings = list(payload.get("warnings") or [])
    error_code: str | None = None
    exit_code: int | None = None
    if gate.get("login"):
        warnings.append("login_gate_detected")
        error_code = "login_required"
        exit_code = 3
    if gate.get("verify"):
        warnings.append("verification_gate_detected")
        error_code = "verification_required"
        exit_code = 4
    if gate.get("blocked"):
        warnings.append("blocked_or_rate_limited")
        error_code = "blocked_or_rate_limited"
        exit_code = 5
    payload["warnings"] = warnings
    payload["gate"] = gate
    if error_code:
        payload["ok"] = False
        payload["exit_code"] = exit_code
        payload["error"] = {
            "code": error_code,
            "message": "Dianping returned a login, verification, or rate-limit gate.",
            "details": {
                "gate": gate,
                "page": payload.get("page"),
                "http": payload.get("http"),
            },
        }
        payload["next_actions"] = [
            "Open Dianping in Edge and complete login/verification, then retry browser mode.",
            "Reduce request frequency if verification or rate limiting appears.",
        ]
    return payload


def with_review_unavailability(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("ok") is False or payload.get("count", 0) > 0:
        return payload
    access = payload.get("review_access") if isinstance(payload.get("review_access"), dict) else {}
    api_probe = access.get("api_probe") if isinstance(access.get("api_probe"), dict) else {}
    app_required = bool(access.get("app_required"))
    status = api_probe.get("status")
    warnings = list(payload.get("warnings") or [])
    warnings.append("review_content_unavailable")
    payload["warnings"] = warnings
    payload["ok"] = False
    payload["exit_code"] = 6
    if status == 403:
        code = "review_api_forbidden"
        message = "Dianping review text is not available from the web page; the page review API returned 403."
    elif app_required:
        code = "app_required_for_reviews"
        message = "Dianping review text is not available from the web page; the page directs users to the app."
    else:
        code = "review_content_unavailable"
        message = "Dianping review text was not found in the rendered page or HTTP response."
    payload["error"] = {
        "code": code,
        "message": message,
        "details": {
            "shop_id": payload.get("shop_id"),
            "review_access": access,
            "page": payload.get("page"),
            "http": payload.get("http"),
        },
    }
    payload["next_actions"] = [
        "Do not treat review_count as review text.",
        "Use the Dianping app or another source if full review bodies are required.",
        "Retry later only if the web page starts rendering review DOM items.",
    ]
    return payload


def browser_search(args: argparse.Namespace, city_id: int) -> dict[str, Any]:
    url = search_url(args.keyword, city_id)
    cdp = CdpProxy(args.cdp_base, args.timeout)
    target = cdp.new(url)
    try:
        time.sleep(args.wait)
        data = cdp.eval_json(target, BROWSER_SEARCH_JS)
    finally:
        if not args.keep_tab:
            cdp.close(target)
    if not isinstance(data, dict):
        raise AgentError("browser_parse_error", "Browser extraction did not return an object", exit_code=6, details={"data": data})
    items = data.get("items") if isinstance(data.get("items"), list) else []
    limited = items[: args.limit]
    payload = base_payload(
        "search",
        mode="browser",
        city_id=city_id,
        keyword=args.keyword,
        url=url,
        count=len(limited),
        items=limited,
        page={"title": data.get("page_title"), "url": data.get("page_url")},
        warnings=[],
    )
    return with_gate_warnings(payload, data.get("gate") if isinstance(data.get("gate"), dict) else {})


def http_search(args: argparse.Namespace, city_id: int) -> dict[str, Any]:
    url = search_url(args.keyword, city_id)
    cache = Cache(args.cache_dir, not args.no_cache)
    cache_key = json.dumps({"cmd": "search", "mode": "http", "url": url, "limit": args.limit}, sort_keys=True)
    cached = cache.get(cache_key, args.cache_ttl)
    if cached:
        cached["cache"] = {"hit": True, "ttl_seconds": args.cache_ttl}
        return cached

    result, cookie_status = http_get(
        url,
        cookie_file=args.cookie_file,
        timeout=args.timeout,
        state_dir=args.state_dir,
        min_interval=args.rate_limit,
    )
    gate = detect_gate(result.body, result.final_url)
    items, warnings = parse_search_html(result.body, limit=args.limit)
    payload = base_payload(
        "search",
        mode="http",
        city_id=city_id,
        keyword=args.keyword,
        url=url,
        http={"status": result.status, "final_url": result.final_url},
        auth=cookie_status,
        count=len(items),
        items=items,
        warnings=warnings,
        cache={"hit": False, "ttl_seconds": args.cache_ttl},
    )
    payload = with_gate_warnings(payload, gate)
    cache.set(cache_key, payload)
    return payload


def cmd_search(args: argparse.Namespace) -> dict[str, Any]:
    city_id = parse_city(args.city)
    if args.mode == "browser":
        return browser_search(args, city_id)
    if args.mode == "http":
        return http_search(args, city_id)
    cdp = CdpProxy(args.cdp_base, args.timeout)
    if cdp.ping():
        return browser_search(args, city_id)
    payload = http_search(args, city_id)
    warnings = list(payload.get("warnings") or [])
    warnings.append("browser_unavailable_fell_back_to_http")
    payload["warnings"] = warnings
    return payload


def browser_shop(args: argparse.Namespace) -> dict[str, Any]:
    url = shop_url(args.shop_id)
    cdp = CdpProxy(args.cdp_base, args.timeout)
    target = cdp.new(url)
    try:
        time.sleep(args.wait)
        data = cdp.eval_json(target, BROWSER_SHOP_JS)
    finally:
        if not args.keep_tab:
            cdp.close(target)
    if not isinstance(data, dict):
        raise AgentError("browser_parse_error", "Browser extraction did not return an object", exit_code=6, details={"data": data})
    item = {
        "shop_id": args.shop_id,
        "name": data.get("title"),
        "rating": data.get("rating"),
        "review_count": data.get("review_count"),
        "avg_price": data.get("avg_price"),
        "category_area": data.get("category_area"),
        "business_hours": data.get("business_hours"),
        "address": data.get("address"),
        "nearby": data.get("nearby"),
        "url": url,
        "page_url": data.get("page_url"),
        "json_ld": data.get("json_ld"),
        "text_sample": data.get("text_sample"),
    }
    payload = base_payload(
        "shop",
        mode="browser",
        shop_id=args.shop_id,
        item=item,
        page={"title": data.get("page_title"), "url": data.get("page_url")},
        warnings=[],
    )
    return with_gate_warnings(payload, data.get("gate") if isinstance(data.get("gate"), dict) else {})


def http_shop(args: argparse.Namespace) -> dict[str, Any]:
    url = shop_url(args.shop_id)
    cache = Cache(args.cache_dir, not args.no_cache)
    cache_key = json.dumps({"cmd": "shop", "mode": "http", "url": url}, sort_keys=True)
    cached = cache.get(cache_key, args.cache_ttl)
    if cached:
        cached["cache"] = {"hit": True, "ttl_seconds": args.cache_ttl}
        return cached
    result, cookie_status = http_get(
        url,
        cookie_file=args.cookie_file,
        timeout=args.timeout,
        state_dir=args.state_dir,
        min_interval=args.rate_limit,
    )
    item, warnings = parse_shop_html(result.body, shop_id=args.shop_id)
    payload = base_payload(
        "shop",
        mode="http",
        shop_id=args.shop_id,
        http={"status": result.status, "final_url": result.final_url},
        auth=cookie_status,
        item=item,
        warnings=warnings,
        cache={"hit": False, "ttl_seconds": args.cache_ttl},
    )
    payload = with_gate_warnings(payload, detect_gate(result.body, result.final_url))
    cache.set(cache_key, payload)
    return payload


def cmd_shop(args: argparse.Namespace) -> dict[str, Any]:
    if args.mode == "browser":
        return browser_shop(args)
    if args.mode == "http":
        return http_shop(args)
    cdp = CdpProxy(args.cdp_base, args.timeout)
    if cdp.ping():
        return browser_shop(args)
    payload = http_shop(args)
    warnings = list(payload.get("warnings") or [])
    warnings.append("browser_unavailable_fell_back_to_http")
    payload["warnings"] = warnings
    return payload


def browser_reviews(args: argparse.Namespace) -> dict[str, Any]:
    url = shop_url(args.shop_id)
    cdp = CdpProxy(args.cdp_base, args.timeout)
    target = cdp.new(url)
    try:
        time.sleep(args.wait)
        cdp.eval_json(target, 'window.scrollTo(0, document.body.scrollHeight); "scrolled"')
        time.sleep(min(max(args.wait / 2, 1.0), 3.0))
        data = cdp.eval_json(target, BROWSER_REVIEWS_JS)
    finally:
        if not args.keep_tab:
            cdp.close(target)
    if not isinstance(data, dict):
        raise AgentError("browser_parse_error", "Browser extraction did not return an object", exit_code=6, details={"data": data})
    items = data.get("items") if isinstance(data.get("items"), list) else []
    limited = items[: args.limit]
    review_access = {
        "app_required": bool(data.get("app_required")),
        "review_root": data.get("review_root"),
        "review_api_url": data.get("review_api_url"),
        "api_probe": data.get("api_probe"),
        "resource_hits": data.get("resource_hits"),
    }
    payload = base_payload(
        "reviews",
        mode="browser",
        shop_id=args.shop_id,
        url=url,
        count=len(limited),
        items=limited,
        review_access=review_access,
        page={"title": data.get("page_title"), "url": data.get("page_url")},
        text_sample=data.get("text_sample"),
        warnings=[],
    )
    payload = with_gate_warnings(payload, data.get("gate") if isinstance(data.get("gate"), dict) else {})
    return with_review_unavailability(payload)


def http_reviews(args: argparse.Namespace) -> dict[str, Any]:
    url = shop_url(args.shop_id)
    cache = Cache(args.cache_dir, not args.no_cache)
    cache_key = json.dumps({"cmd": "reviews", "mode": "http", "url": url, "limit": args.limit}, sort_keys=True)
    cached = cache.get(cache_key, args.cache_ttl)
    if cached:
        cached["cache"] = {"hit": True, "ttl_seconds": args.cache_ttl}
        return cached
    result, cookie_status = http_get(
        url,
        cookie_file=args.cookie_file,
        timeout=args.timeout,
        state_dir=args.state_dir,
        min_interval=args.rate_limit,
    )
    items, warnings = parse_reviews_html(result.body, limit=args.limit)
    app_required = bool(re.search(r"移步至大众点评App|打开大众点评App|去大众点评App查看|App查看|扫码", result.body))
    payload = base_payload(
        "reviews",
        mode="http",
        shop_id=args.shop_id,
        url=url,
        http={"status": result.status, "final_url": result.final_url},
        auth=cookie_status,
        count=len(items),
        items=items,
        review_access={"app_required": app_required, "review_root": None, "review_api_url": None, "api_probe": None},
        warnings=warnings,
        cache={"hit": False, "ttl_seconds": args.cache_ttl},
    )
    payload = with_gate_warnings(payload, detect_gate(result.body, result.final_url))
    payload = with_review_unavailability(payload)
    cache.set(cache_key, payload)
    return payload


def cmd_reviews(args: argparse.Namespace) -> dict[str, Any]:
    if args.mode == "browser":
        return browser_reviews(args)
    if args.mode == "http":
        return http_reviews(args)
    cdp = CdpProxy(args.cdp_base, args.timeout)
    if cdp.ping():
        return browser_reviews(args)
    payload = http_reviews(args)
    warnings = list(payload.get("warnings") or [])
    warnings.append("browser_unavailable_fell_back_to_http")
    payload["warnings"] = warnings
    return payload


def cmd_cities(args: argparse.Namespace) -> dict[str, Any]:
    cities = [{"alias": alias, "city_id": city_id} for alias, city_id in sorted(CITY_ALIASES.items())]
    return base_payload("cities", default_city_id=DEFAULT_CITY_ID, cities=cities)


def cmd_auth_status(args: argparse.Namespace) -> dict[str, Any]:
    _header, status = load_cookie_header(args.cookie_file)
    safe = bool(status["exists"] and status["has_dper"] and status["has_dplet"] and status["mode"] in {"0o600", "0o400"})
    warnings: list[str] = []
    if status["exists"] and status["mode"] not in {"0o600", "0o400"}:
        warnings.append("cookie_file_permissions_too_open")
    if not status["has_dper"] or not status["has_dplet"]:
        warnings.append("dper_or_dplet_missing")
    return base_payload("auth status", auth=status, safe=safe, warnings=warnings)


def cmd_auth_import(args: argparse.Namespace) -> dict[str, Any]:
    raw = sys.stdin.read()
    cookies = parse_cookie_header(raw)
    missing = [key for key in ("dper", "dplet") if not cookies.get(key)]
    if missing:
        raise AgentError(
            "missing_required_cookies",
            "Cookie input must include dper and dplet",
            exit_code=2,
            details={"missing": missing},
            next_actions=["Pipe a Cookie header into `dp auth import --stdin`; do not paste cookie values into chat logs."],
        )
    selected = {key: cookies[key] for key in ("dper", "dplet") if key in cookies}
    for optional in ("_lxsdk_cuid", "_lxsdk"):
        if cookies.get(optional):
            selected[optional] = cookies[optional]
    payload = {
        "version": 1,
        "source": "stdin_cookie_header",
        "created_at": now_iso(),
        "cookies": selected,
    }
    atomic_write_text(args.cookie_file, json.dumps(payload, ensure_ascii=False, indent=2) + "\n", mode=0o600)
    return base_payload(
        "auth import",
        auth={
            **local_file_status(args.cookie_file, DEFAULT_COOKIE_FILE, "DP_COOKIE_FILE"),
            "stored_keys": sorted(selected),
            "has_dper": True,
            "has_dplet": True,
        },
        warnings=[],
    )


def tcp_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def cmd_doctor(args: argparse.Namespace) -> dict[str, Any]:
    cdp_url = urllib.parse.urlparse(args.cdp_base)
    host = cdp_url.hostname or "127.0.0.1"
    port = cdp_url.port or (443 if cdp_url.scheme == "https" else 80)
    cdp_tcp = tcp_open(host, port)
    cdp_ping = CdpProxy(args.cdp_base, args.timeout).ping() if cdp_tcp else False
    _header, auth = load_cookie_header(args.cookie_file)
    checks = {
        "python": {"version": sys.version.split()[0], "ok": sys.version_info >= (3, 10)},
        "state_dir": {
            "source": path_source(args.state_dir, DEFAULT_STATE_DIR, "DP_STATE_DIR"),
            "exists": args.state_dir.exists(),
        },
        "cache_dir": {
            "source": path_source(args.cache_dir, DEFAULT_CACHE_DIR, "DP_CACHE_DIR"),
            "exists": args.cache_dir.exists(),
        },
        "cookie_file": auth,
        "cdp_proxy": {"base_url": args.cdp_base, "tcp_open": cdp_tcp, "api_ok": cdp_ping},
    }
    warnings: list[str] = []
    if auth["exists"] and auth["mode"] not in {"0o600", "0o400"}:
        warnings.append("cookie_file_permissions_too_open")
    if not cdp_ping:
        warnings.append("cdp_proxy_unavailable")
    ok = checks["python"]["ok"] and (cdp_ping or (auth["has_dper"] and auth["has_dplet"]))
    payload = base_payload(
        "doctor",
        ok=ok,
        checks=checks,
        warnings=warnings,
        next_actions=[] if ok else ["Use Edge/CDP browser mode or import dper+dplet with `dp auth import --stdin`."],
    )
    if not ok:
        payload["exit_code"] = 5
        payload["error"] = {
            "code": "runtime_unavailable",
            "message": "Neither Edge/CDP browser mode nor HTTP cookie auth is available.",
            "details": {"cdp_proxy": checks["cdp_proxy"], "cookie_file": auth},
        }
    return payload


def emit(payload: dict[str, Any], args: argparse.Namespace) -> None:
    fmt = getattr(args, "format", "json")
    indent = 2 if getattr(args, "pretty", False) else None
    if fmt == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=indent, sort_keys=False))
        return
    if payload.get("ok") is False:
        error = payload.get("error", {})
        print(f"ERROR {error.get('code')}: {error.get('message')}")
        return
    command = payload.get("command")
    if command == "search":
        print(f"{payload.get('keyword')} city={payload.get('city_id')} mode={payload.get('mode')}")
        for idx, item in enumerate(payload.get("items") or [], 1):
            facts = []
            if item.get("avg_price"):
                facts.append(f"人均¥{item.get('avg_price')}")
            if item.get("review_count"):
                facts.append(f"{item.get('review_count')}条评价")
            if item.get("category"):
                facts.append(str(item.get("category")))
            if item.get("area"):
                facts.append(str(item.get("area")))
            suffix = f" ({' | '.join(facts)})" if facts else ""
            print(f"{idx}. {item.get('name')} [{item.get('shop_id')}]{suffix} {item.get('url')}")
    elif command == "shop":
        item = payload.get("item") or {}
        print(f"{item.get('name')} [{item.get('shop_id')}]")
        facts = []
        if item.get("rating"):
            facts.append(f"评分{item.get('rating')}")
        if item.get("avg_price"):
            facts.append(f"人均¥{item.get('avg_price')}")
        if item.get("review_count"):
            facts.append(f"{item.get('review_count')}条评价")
        if item.get("business_hours"):
            facts.append(str(item.get("business_hours")))
        if facts:
            print(" | ".join(facts))
        if item.get("address"):
            print(f"address: {item.get('address')}")
        if item.get("nearby"):
            print(f"nearby: {item.get('nearby')}")
        print(item.get("url"))
    elif command == "reviews":
        print(f"reviews [{payload.get('shop_id')}] mode={payload.get('mode')} count={payload.get('count')}")
        for idx, item in enumerate(payload.get("items") or [], 1):
            facts = []
            if item.get("date"):
                facts.append(str(item.get("date")))
            if item.get("rating"):
                facts.append(f"评分{item.get('rating')}")
            if item.get("author"):
                facts.append(str(item.get("author")))
            suffix = f" ({' | '.join(facts)})" if facts else ""
            print(f"{idx}. {item.get('body')}{suffix}")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


def error_payload(exc: AgentError) -> dict[str, Any]:
    return {
        "ok": False,
        "tool": APP_NAME,
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "error": {
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
        },
        "next_actions": exc.next_actions,
    }


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=("json", "text"), default=os.environ.get("DP_FORMAT", "json"))
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--cookie-file", type=Path, default=DEFAULT_COOKIE_FILE)
    parser.add_argument("--cdp-base", default=DEFAULT_CDP_BASE)


def add_fetch_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mode", choices=("browser", "http", "auto"), default=os.environ.get("DP_MODE", "browser"))
    parser.add_argument("--wait", type=float, default=float(os.environ.get("DP_BROWSER_WAIT", "4.0")))
    parser.add_argument("--keep-tab", action="store_true", help="Leave the browser tab open for manual inspection.")
    parser.add_argument("--cache-ttl", type=int, default=int(os.environ.get("DP_CACHE_TTL", "1800")))
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--rate-limit", type=float, default=DEFAULT_RATE_LIMIT_SECONDS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dp",
        description="Agent-friendly read-only Dianping CLI.",
    )
    add_common_args(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search", help="Search Dianping shops.")
    add_common_args(p_search)
    add_fetch_args(p_search)
    p_search.add_argument("keyword")
    p_search.add_argument("--city", default=str(DEFAULT_CITY_ID), help="Dianping city_id or alias. Default: 15/xiamen.")
    p_search.add_argument("--limit", type=int, default=10)
    p_search.set_defaults(func=cmd_search)

    p_shop = sub.add_parser("shop", help="Read a Dianping shop page.")
    add_common_args(p_shop)
    add_fetch_args(p_shop)
    p_shop.add_argument("shop_id")
    p_shop.set_defaults(func=cmd_shop)

    p_reviews = sub.add_parser("reviews", help="Read rendered Dianping review text when the web page exposes it.")
    add_common_args(p_reviews)
    add_fetch_args(p_reviews)
    p_reviews.add_argument("shop_id")
    p_reviews.add_argument("--limit", type=int, default=10)
    p_reviews.set_defaults(func=cmd_reviews)

    p_cities = sub.add_parser("cities", help="List built-in city aliases.")
    add_common_args(p_cities)
    p_cities.set_defaults(func=cmd_cities)

    p_doctor = sub.add_parser("doctor", help="Check local runtime state.")
    add_common_args(p_doctor)
    p_doctor.set_defaults(func=cmd_doctor)

    p_auth = sub.add_parser("auth", help="Manage local HTTP cookie auth without exporting secrets.")
    add_common_args(p_auth)
    auth_sub = p_auth.add_subparsers(dest="auth_command", required=True)

    p_auth_status = auth_sub.add_parser("status", help="Show sanitized cookie-file status.")
    add_common_args(p_auth_status)
    p_auth_status.set_defaults(func=cmd_auth_status)

    p_auth_import = auth_sub.add_parser("import", help="Import dper/dplet from stdin. No export command exists.")
    add_common_args(p_auth_import)
    p_auth_import.add_argument("--stdin", action="store_true", required=True, help="Required explicit acknowledgement.")
    p_auth_import.set_defaults(func=cmd_auth_import)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = args.func(args)
        emit(payload, args)
        return 0 if payload.get("ok", True) else int(payload.get("exit_code") or 1)
    except AgentError as exc:
        emit(error_payload(exc), args)
        return exc.exit_code
    except KeyboardInterrupt:
        emit(error_payload(AgentError("interrupted", "Interrupted", exit_code=130)), args)
        return 130
    except Exception as exc:  # Last-resort JSON error keeps agent callers parseable.
        emit(
            error_payload(
                AgentError(
                    "internal_error",
                    "Unhandled internal error",
                    exit_code=70,
                    details={"type": type(exc).__name__, "message": str(exc)},
                )
            ),
            args,
        )
        return 70


if __name__ == "__main__":
    raise SystemExit(main())
