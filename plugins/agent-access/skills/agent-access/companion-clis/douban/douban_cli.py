#!/usr/bin/env python3
"""Agent-friendly Douban CLI for babata.

The CLI uses the user's Edge CDP session as the auth/session boundary. It does
not export or persist Douban cookies. Output is always a JSON envelope.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


APP_NAME = "douban-cli"
SCHEMA_VERSION = 1
DEFAULT_CDP_BASE = os.environ.get("DOUBAN_CDP_BASE", "http://127.0.0.1:3456")
DEFAULT_TIMEOUT = float(os.environ.get("DOUBAN_TIMEOUT", "30"))
DEFAULT_CITY = os.environ.get("DOUBAN_CITY", "shanghai")
DOUBAN_LOGIN_URL = "https://accounts.douban.com/passport/login"

INTEREST_ALIASES = {
    "wish": "wish",
    "want": "wish",
    "想看": "wish",
    "collect": "collect",
    "watched": "collect",
    "watch": "collect",
    "done": "collect",
    "看过": "collect",
    "do": "do",
    "watching": "do",
    "在看": "do",
}

INTEREST_LABELS = {
    "wish": "想看",
    "collect": "看过",
    "do": "在看",
}

CITY_ALIASES = {
    "sh": "shanghai",
    "shanghai": "shanghai",
    "上海": "shanghai",
    "bj": "beijing",
    "beijing": "beijing",
    "北京": "beijing",
    "gz": "guangzhou",
    "guangzhou": "guangzhou",
    "广州": "guangzhou",
    "sz": "shenzhen",
    "shenzhen": "shenzhen",
    "深圳": "shenzhen",
    "hz": "hangzhou",
    "hangzhou": "hangzhou",
    "杭州": "hangzhou",
    "cd": "chengdu",
    "chengdu": "chengdu",
    "成都": "chengdu",
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
class CdpTarget:
    target_id: str
    created: bool


@dataclasses.dataclass
class ResolvedSubject:
    subject_id: str
    input: str
    input_kind: str
    method: str
    title: str | None = None
    year: str | None = None
    url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_id": self.subject_id,
            "input": self.input,
            "input_kind": self.input_kind,
            "method": self.method,
            "title": self.title,
            "year": self.year,
            "url": self.url or f"https://movie.douban.com/subject/{self.subject_id}/",
        }


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def strip_tags(value: str) -> str:
    return compact_text(re.sub(r"<[^>]+>", " ", value or ""))


def subject_id(value: str) -> str:
    match = re.search(r"(?:subject/)?(\d{3,})", value)
    if not match:
        raise AgentError(
            "invalid_subject",
            f"Could not parse Douban subject id from {value!r}",
            exit_code=2,
            next_actions=["Pass a numeric subject id or a movie.douban.com/subject/... URL."],
        )
    return match.group(1)


def direct_subject_id(value: str) -> str | None:
    match = re.search(r"(?:subject/)?(\d{3,})", value or "")
    return match.group(1) if match else None


def resolved_direct_subject(value: str) -> ResolvedSubject | None:
    sid = direct_subject_id(value)
    if not sid:
        return None
    input_kind = "url" if "subject/" in value else "id"
    return ResolvedSubject(
        subject_id=sid,
        input=value,
        input_kind=input_kind,
        method="direct",
        url=f"https://movie.douban.com/subject/{sid}/",
    )


def normalize_city(value: str | None) -> str:
    if not value:
        return DEFAULT_CITY
    key = value.strip().lower()
    return CITY_ALIASES.get(key, key)


def normalize_interest(value: str) -> str:
    key = (value or "").strip().lower()
    interest = INTEREST_ALIASES.get(key)
    if not interest:
        raise AgentError(
            "invalid_interest",
            f"Unsupported Douban interest value: {value!r}",
            exit_code=2,
            next_actions=["Use one of: wish, collect, do, 想看, 看过, 在看."],
        )
    return interest


def normalize_rating(value: int | None) -> int | None:
    if value is None:
        return None
    if value < 1 or value > 5:
        raise AgentError(
            "invalid_rating",
            "Douban rating must be an integer from 1 to 5.",
            exit_code=2,
            next_actions=["Use --rating 1..5. 1=很差, 2=较差, 3=还行, 4=推荐, 5=力荐."],
        )
    return value


def require_rating_interest_compatible(interest: str, rating: int | None) -> None:
    if rating is not None and interest != "collect":
        raise AgentError(
            "rating_requires_collect",
            "Douban movie ratings are only supported with the 看过/collect state.",
            exit_code=2,
            next_actions=["Use `douban mark SUBJECT collect --rating N --apply` or `douban rate SUBJECT --rating N --apply`."],
        )


def json_envelope(command: str, data: Any, *, warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        "ok": True,
        "tool": APP_NAME,
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "generated_at": now_iso(),
        "data": data,
        "warnings": warnings or [],
    }


def write_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def fail(error: AgentError) -> None:
    write_json(
        {
            "ok": False,
            "tool": APP_NAME,
            "schema_version": SCHEMA_VERSION,
            "generated_at": now_iso(),
            "error": {
                "code": error.code,
                "message": error.message,
                "details": error.details,
                "next_actions": error.next_actions,
            },
        }
    )
    raise SystemExit(error.exit_code)


class CdpProxy:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, path: str, *, data: str | bytes | None = None) -> Any:
        url = self.base_url + path
        body = data.encode("utf-8") if isinstance(data, str) else data
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
                    "Run `agent-access doctor douban` and check the Agent Access browser/CDP reference.",
                    "Make sure the user's Edge CDP LaunchAgent is running on 127.0.0.1:9222.",
                ],
            ) from exc
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise AgentError(
                "cdp_bad_response",
                "CDP proxy returned non-JSON response",
                exit_code=5,
                details={"sample": text[:400]},
            ) from exc

    def health(self) -> dict[str, Any]:
        return self._request("/health")

    def targets(self) -> list[dict[str, Any]]:
        data = self._request("/targets")
        return data if isinstance(data, list) else []

    def new(self, url: str) -> CdpTarget:
        encoded = urllib.parse.urlencode({"url": url})
        data = self._request(f"/new?{encoded}")
        target_id = data.get("targetId") if isinstance(data, dict) else None
        if not target_id:
            raise AgentError("cdp_new_failed", "Failed to create Edge tab", exit_code=5, details={"response": data})
        return CdpTarget(str(target_id), True)

    def close(self, target_id: str) -> None:
        try:
            self._request(f"/close?target={urllib.parse.quote(target_id)}")
        except AgentError:
            pass

    def navigate(self, target_id: str, url: str) -> None:
        encoded = urllib.parse.urlencode({"target": target_id, "url": url})
        self._request(f"/navigate?{encoded}")

    def info(self, target_id: str) -> dict[str, Any]:
        data = self._request(f"/info?target={urllib.parse.quote(target_id)}")
        return data if isinstance(data, dict) else {}

    def eval(self, target_id: str, script: str) -> Any:
        data = self._request(f"/eval?target={urllib.parse.quote(target_id)}", data=script)
        value = data.get("value") if isinstance(data, dict) else data
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value


class BrowserSession:
    def __init__(self, proxy: CdpProxy, keep_tab: bool = False) -> None:
        self.proxy = proxy
        self.keep_tab = keep_tab
        self.target: CdpTarget | None = None

    def __enter__(self) -> "BrowserSession":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.target and self.target.created and not self.keep_tab:
            self.proxy.close(self.target.target_id)

    def open(self, url: str) -> str:
        self.target = self.proxy.new("about:blank")
        self.proxy.navigate(self.target.target_id, url)
        return self.target.target_id

    def current_target(self) -> str:
        if not self.target:
            raise AgentError("no_browser_target", "No CDP target has been opened", exit_code=5)
        return self.target.target_id

    def navigate(self, url: str) -> None:
        if not self.target:
            self.open(url)
        else:
            self.proxy.navigate(self.target.target_id, url)

    def eval(self, script: str) -> Any:
        return self.proxy.eval(self.current_target(), script)

    def info(self) -> dict[str, Any]:
        return self.proxy.info(self.current_target())


class NowPlayingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "li":
            return
        attrs_dict = {k: v or "" for k, v in attrs}
        if "list-item" not in attrs_dict.get("class", ""):
            return
        subject = attrs_dict.get("data-subject")
        if not subject:
            return
        score_raw = attrs_dict.get("data-score") or "0"
        try:
            score = float(score_raw)
        except ValueError:
            score = 0.0
        release = attrs_dict.get("data-release") or None
        self.items.append(
            {
                "subject_id": subject,
                "title": attrs_dict.get("data-title") or None,
                "score": score,
                "rating": score,
                "release": release,
                "year": release,
                "duration": attrs_dict.get("data-duration") or None,
                "region": attrs_dict.get("data-region") or None,
                "director": attrs_dict.get("data-director") or None,
                "actors": attrs_dict.get("data-actors") or None,
                "category": attrs_dict.get("data-category") or None,
                "url": f"https://movie.douban.com/subject/{subject}/",
            }
        )


def parse_nowplaying_html(body: str) -> list[dict[str, Any]]:
    parser = NowPlayingParser()
    parser.feed(body)
    return parser.items


def parse_interest_html(body: str) -> dict[str, Any]:
    lowered = body or ""
    status = "unmarked"
    if "我看过这部电影" in lowered:
        status = "collect"
    elif "我想看这部电影" in lowered:
        status = "wish"
    elif "我在看这部电影" in lowered:
        status = "do"
    date_match = re.search(r'<span[^>]+class=["\']collection_date["\'][^>]*>([^<]+)</span>', body or "")
    rating_match = re.search(r"rating([1-5])-t", body or "")
    if not rating_match:
        rating_match = re.search(r"allstar([1-5])0", body or "")
    if status == "unmarked":
        my_rating = None
    elif not rating_match:
        star_ids = [int(value) for value in re.findall(r'id=["\']star([1-5])["\']', body or "")]
        my_rating = max(star_ids) if star_ids else None
    else:
        my_rating = int(rating_match.group(1))
    return {
        "interest": status,
        "marked": status != "unmarked",
        "my_rating": my_rating,
        "collection_date": compact_text(date_match.group(1)) if date_match else None,
    }


def filter_nowplaying_items(
    items: list[dict[str, Any]],
    *,
    new_only: bool = False,
    year: str | int | None = None,
) -> list[dict[str, Any]]:
    if not new_only and year in (None, ""):
        return items
    target_year = str(year or dt.datetime.now().year)
    return [
        item
        for item in items
        if str(item.get("year") or item.get("release") or "").startswith(target_year)
    ]


def parse_movie_html(body: str, sid: str) -> dict[str, Any]:
    title = None
    title_match = re.search(r'<span[^>]+property=["\']v:itemreviewed["\'][^>]*>(.*?)</span>', body, re.I)
    if title_match:
        title = compact_text(title_match.group(1))
    if not title:
        h1_match = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", body, re.I)
        title = strip_tags(h1_match.group(1)) if h1_match else None
    rating_match = re.search(r'<strong[^>]+class=["\'][^"\']*rating_num[^"\']*["\'][^>]*>([\d.]+)</strong>', body, re.I)
    people_match = re.search(r'<a[^>]+class=["\']rating_people["\'][^>]*>[\s\S]*?<span[^>]*>([\d,]+)</span>', body, re.I)
    year_match = re.search(r'<span[^>]+class=["\']year["\'][^>]*>\((\d{4})\)</span>', body, re.I)
    rating = float(rating_match.group(1)) if rating_match else 0.0
    rating_people = int(people_match.group(1).replace(",", "")) if people_match else None
    return {
        "subject_id": sid,
        "title": title,
        "year": year_match.group(1) if year_match else None,
        "rating": rating,
        "rating_people": rating_people,
        "url": f"https://movie.douban.com/subject/{sid}/",
    }


def extract_uid_from_url(url: str) -> str | None:
    match = re.search(r"douban\.com/people/([^/?#]+)/?", url or "")
    return match.group(1) if match else None


def browser_auth_status(session: BrowserSession) -> dict[str, Any]:
    session.open("https://www.douban.com/mine/")
    info = session.info()
    url = str(info.get("url") or "")
    uid = extract_uid_from_url(url)
    logged_in = bool(uid)
    if not logged_in:
        sample = session.eval(
            """(() => JSON.stringify({
              title: document.title,
              url: location.href,
              text: (document.body && document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 240)
            }))()"""
        )
        if isinstance(sample, dict):
            url = str(sample.get("url") or url)
    return {
        "authenticated": logged_in,
        "profile": {"uid": "[REDACTED]" if uid else None},
        "method": "edge-cdp",
        "url_kind": "people" if logged_in else "login_or_unknown",
        "next_action": None if logged_in else "Open Edge and log in to Douban, then rerun `douban auth status`.",
    }


def detect_douban_gate(page_url: str, text: str = "", html_text: str = "") -> dict[str, Any]:
    haystack = f"{page_url}\n{text}\n{html_text[:1000]}"
    login_page = bool(re.search(r"accounts\.douban\.com|passport/login", page_url, re.I))
    return {
        "login": bool(re.search(r"accounts\.douban\.com|passport/login|请登录|登录后|登录豆瓣|账号登录|帐号登录|扫码登录|手机验证码登录", haystack, re.I)),
        "security": False if login_page else bool(re.search(r"sec\.douban\.com|检测到有异常请求|安全|验证|验证码|captcha|abnormal", haystack, re.I)),
        "blocked": bool(re.search(r"403|禁止访问|访问过于频繁|sec\.douban\.com", haystack, re.I)),
    }


def require_not_blocked(gate: dict[str, Any], *, page_url: str, command: str) -> None:
    if gate.get("security") or gate.get("blocked"):
        raise AgentError(
            "douban_security_gate",
            f"Douban returned a security/verification page during {command}.",
            exit_code=6,
            details={"page_url": page_url, "gate": gate},
            next_actions=[
                "Open the page in the user's Edge, complete Douban verification manually, then rerun the command.",
                "Avoid repeatedly retrying; repeated automated access can worsen Douban risk controls.",
            ],
        )


def require_expected_url(page_url: str, *, expected: str, command: str) -> None:
    if expected in page_url:
        return
    raise AgentError(
        "page_not_loaded",
        f"Douban {command} page did not load the expected URL.",
        exit_code=5,
        details={"page_url": page_url, "expected": expected},
        next_actions=[
            "Run `douban doctor` to confirm Edge CDP is healthy.",
            "Rerun with --keep-tab and inspect the opened Edge page.",
        ],
    )


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def build_apply_command(
    sid: str,
    *,
    interest: str,
    rating: int | None,
    comment: str,
    tags: str,
    private: bool,
) -> str:
    parts = ["douban", "mark", sid, interest]
    if rating is not None:
        parts.extend(["--rating", str(rating)])
    if comment:
        parts.extend(["--comment", shell_quote(comment)])
    if tags:
        parts.extend(["--tags", shell_quote(tags)])
    if private:
        parts.append("--private")
    parts.append("--apply")
    return " ".join(parts)


def browser_nowplaying(session: BrowserSession, *, city: str, limit: int, include_zero: bool) -> dict[str, Any]:
    city_slug = normalize_city(city)
    url = f"https://movie.douban.com/cinema/nowplaying/{urllib.parse.quote(city_slug)}/"
    session.open(url)
    result = session.eval(
        r"""(() => {
          const html = document.documentElement.outerHTML || "";
          const text = (document.body && document.body.innerText || "").replace(/\s+/g, " ").trim();
          return JSON.stringify({
            title: document.title,
            url: location.href,
            html,
            gate: {
              login: /登录|请登录|passport\/login/.test(text + location.href),
              blocked: /403|禁止访问|检测到有异常请求|验证|验证码|安全/.test(text)
            },
            text_sample: text.slice(0, 300)
          });
        })()"""
    )
    if not isinstance(result, dict):
        raise AgentError("browser_parse_failed", "Could not read Douban nowplaying page", exit_code=5, details={"result": result})
    page_url = str(result.get("url") or "")
    require_expected_url(page_url, expected="movie.douban.com/cinema/nowplaying", command="nowplaying")
    gate = detect_douban_gate(str(result.get("url") or ""), str(result.get("text_sample") or ""), str(result.get("html") or ""))
    require_not_blocked(gate, page_url=str(result.get("url") or url), command="nowplaying")
    items = parse_nowplaying_html(str(result.get("html") or ""))
    if not include_zero:
        items = [item for item in items if float(item.get("score") or 0) > 0]
    items = sorted(items, key=lambda item: float(item.get("score") or 0), reverse=True)
    if not items:
        raise AgentError(
            "nowplaying_parse_empty",
            "Douban nowplaying page loaded but no movie items were parsed.",
            exit_code=5,
            details={"page_url": page_url, "gate": gate, "text_sample": result.get("text_sample")},
            next_actions=[
                "Rerun with --include-zero in case all visible movies are unrated.",
                "Rerun with --keep-tab and update site-patterns/douban.com.md if the DOM changed.",
            ],
        )
    return {
        "city": city_slug,
        "url": result.get("url") or url,
        "count": len(items),
        "items": items[:limit],
        "gate": gate,
    }


def browser_recommend_nowplaying(
    session: BrowserSession,
    *,
    city: str,
    limit: int,
    include_zero: bool,
    exclude: set[str],
    new_only: bool,
    year: str | None,
) -> dict[str, Any]:
    nowplaying = browser_nowplaying(session, city=city, limit=500, include_zero=include_zero)
    source_items = nowplaying["items"]
    items = filter_nowplaying_items(source_items, new_only=new_only, year=year)
    selected: list[dict[str, Any]] = []
    checked: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for item in items:
        sid = str(item["subject_id"])
        session.navigate(item["url"])
        status = read_interest_from_current_page(session, sid, command="recommend-nowplaying")
        row = {
            **item,
            "interest": status.get("interest"),
            "marked": status.get("marked"),
            "my_rating": status.get("my_rating"),
            "collection_date": status.get("collection_date"),
        }
        checked.append(row)
        if status.get("interest") in exclude:
            skipped.append(row)
            continue
        selected.append(row)
        if len(selected) >= limit:
            break

    return {
        "city": nowplaying["city"],
        "source_url": nowplaying["url"],
        "source_count": nowplaying["count"],
        "filtered_count": len(items),
        "limit": limit,
        "exclude_interest": sorted(exclude),
        "filters": {
            "new_only": bool(new_only),
            "year": str(year or dt.datetime.now().year) if new_only or year else None,
        },
        "checked_count": len(checked),
        "skipped_count": len(skipped),
        "items": selected,
        "skipped": skipped,
    }


def browser_search(session: BrowserSession, *, query: str, limit: int) -> dict[str, Any]:
    session.open("https://movie.douban.com/")
    result = session.eval(
        f"""(async () => {{
          const query = {json.dumps(query)};
          const response = await fetch(`/j/subject_suggest?q=${{encodeURIComponent(query)}}`, {{
            credentials: "include",
            headers: {{"X-Requested-With": "XMLHttpRequest"}}
          }});
          const text = await response.text();
          let parsed = null;
          try {{ parsed = JSON.parse(text); }} catch (error) {{}}
          return JSON.stringify({{
            ok: response.ok,
            http_status: response.status,
            url: location.href,
            query,
            results: Array.isArray(parsed) ? parsed : [],
            response_text_sample: parsed ? null : text.slice(0, 240)
          }});
        }})()"""
    )
    if not isinstance(result, dict):
        raise AgentError("search_unreadable", "Could not read Douban search response", exit_code=5, details={"result": result})
    if not result.get("ok"):
        raise AgentError(
            "search_failed",
            "Douban subject suggest request failed.",
            exit_code=5,
            details={"response": result},
            next_actions=["Try passing a numeric subject id or full movie.douban.com/subject/... URL."],
        )
    items = []
    for index, raw in enumerate(result.get("results") or [], start=1):
        if not isinstance(raw, dict):
            continue
        sid = str(raw.get("id") or raw.get("episode") or "")
        if not sid:
            url = str(raw.get("url") or "")
            sid = direct_subject_id(url) or ""
        if not sid:
            continue
        title = compact_text(str(raw.get("title") or raw.get("title_sub") or ""))
        subtitle = compact_text(str(raw.get("sub_title") or raw.get("subtitle") or ""))
        year = str(raw.get("year") or "") or None
        rating_value = raw.get("rate") if raw.get("rate") not in (None, "") else raw.get("rating")
        try:
            rating = float(rating_value) if rating_value not in (None, "", "0") else 0.0
        except (TypeError, ValueError):
            rating = 0.0
        items.append(
            {
                "rank": index,
                "subject_id": sid,
                "title": title or None,
                "subtitle": subtitle or None,
                "display_title": compact_text(f"{title} {subtitle}").strip() or title or subtitle or None,
                "year": year,
                "rating": rating,
                "type": raw.get("type") or None,
                "url": f"https://movie.douban.com/subject/{sid}/",
                "raw": {k: v for k, v in raw.items() if k in {"sub_title", "title", "year", "rate", "type"}},
            }
        )
    return {
        "query": query,
        "count": len(items),
        "items": items[:limit],
    }


def resolve_subject(session: BrowserSession, value: str) -> ResolvedSubject:
    direct = resolved_direct_subject(value)
    if direct:
        return direct
    search = browser_search(session, query=value, limit=5)
    items = search.get("items") or []
    if not items:
        raise AgentError(
            "subject_not_found",
            f"Could not resolve Douban movie subject from {value!r}.",
            exit_code=4,
            details={"query": value, "search": search},
            next_actions=["Try `douban search QUERY` and pass the chosen subject_id explicitly."],
        )
    first = items[0]
    return ResolvedSubject(
        subject_id=str(first["subject_id"]),
        input=value,
        input_kind="query",
        method="search_first",
        title=first.get("title"),
        year=first.get("year"),
        url=first.get("url"),
    )


def browser_movie(session: BrowserSession, sid: str) -> dict[str, Any]:
    url = f"https://movie.douban.com/subject/{sid}/"
    session.open(url)
    result = session.eval(
        r"""(() => JSON.stringify({
          title: document.title,
          url: location.href,
          html: document.documentElement.outerHTML || "",
          text_sample: (document.body && document.body.innerText || "").replace(/\s+/g, " ").trim().slice(0, 300)
        }))()"""
    )
    if not isinstance(result, dict):
        raise AgentError("browser_parse_failed", "Could not read Douban movie page", exit_code=5, details={"result": result})
    gate = detect_douban_gate(str(result.get("url") or ""), str(result.get("text_sample") or ""), str(result.get("html") or ""))
    require_not_blocked(gate, page_url=str(result.get("url") or url), command="movie")
    data = parse_movie_html(str(result.get("html") or ""), sid)
    if not data.get("title"):
        raise AgentError(
            "movie_parse_empty",
            "Douban movie page loaded but no movie title was parsed.",
            exit_code=5,
            details={"page_url": result.get("url") or url, "gate": gate, "text_sample": result.get("text_sample")},
            next_actions=["Rerun with --keep-tab and inspect the Edge page, then update site-patterns/douban.com.md if the DOM changed."],
        )
    data["page_url"] = result.get("url") or url
    data["gate"] = gate
    return data


def read_interest_from_current_page(session: BrowserSession, sid: str, *, command: str) -> dict[str, Any]:
    url = f"https://movie.douban.com/subject/{sid}/"
    result = session.eval(
        r"""(() => JSON.stringify({
          title: document.title,
          url: location.href,
          interest_html: (document.querySelector('.j.a_stars') || document.querySelector('#interest_sectl') || {}).outerHTML || "",
          interest_source: document.querySelector('.j.a_stars') ? ".j.a_stars" : (document.querySelector('#interest_sectl') ? "#interest_sectl" : null),
          body_sample: (document.body && document.body.innerText || "").replace(/\s+/g, " ").trim().slice(0, 400)
        }))()"""
    )
    if not isinstance(result, dict):
        raise AgentError("browser_parse_failed", "Could not read Douban interest status", exit_code=5, details={"result": result})
    gate = detect_douban_gate(str(result.get("url") or ""), str(result.get("body_sample") or ""), str(result.get("interest_html") or ""))
    require_not_blocked(gate, page_url=str(result.get("url") or url), command=command)
    interest = parse_interest_html(str(result.get("interest_html") or ""))
    if not result.get("interest_html"):
        text = str(result.get("body_sample") or "")
        if "登录" in text or "请登录" in text:
            interest["auth_required"] = True
            interest["next_action"] = "Open Edge and log in to Douban, then rerun this command."
    return {
        "subject_id": sid,
        "url": result.get("url") or url,
        "gate": gate,
        "interest_source": result.get("interest_source"),
        **interest,
    }


def browser_interest(session: BrowserSession, sid: str) -> dict[str, Any]:
    url = f"https://movie.douban.com/subject/{sid}/"
    session.open(url)
    return read_interest_from_current_page(session, sid, command="status")


def browser_mark_interest(
    session: BrowserSession,
    sid: str,
    *,
    interest: str,
    rating: int | None,
    comment: str,
    tags: str,
    private: bool,
    apply: bool,
) -> dict[str, Any]:
    url = f"https://movie.douban.com/subject/{sid}/"
    session.open(url)
    before = session.eval(
        r"""(() => JSON.stringify({
          title: document.title,
          url: location.href,
          interest_html: (document.querySelector('#interest_sectl') || document.querySelector('.j.a_stars') || {}).outerHTML || "",
          body_sample: (document.body && document.body.innerText || "").replace(/\s+/g, " ").trim().slice(0, 400),
          has_ck: /(?:^|;\s*)ck=/.test(document.cookie || "")
        }))()"""
    )
    if not isinstance(before, dict):
        raise AgentError("browser_parse_failed", "Could not read Douban movie page before marking", exit_code=5, details={"result": before})
    page_url = str(before.get("url") or url)
    gate = detect_douban_gate(page_url, str(before.get("body_sample") or ""), str(before.get("interest_html") or ""))
    require_not_blocked(gate, page_url=page_url, command="mark")
    require_expected_url(page_url, expected=f"movie.douban.com/subject/{sid}", command="mark")

    before_interest = parse_interest_html(str(before.get("interest_html") or ""))
    planned_payload = {
        "interest": interest,
        "interest_label": INTEREST_LABELS.get(interest, interest),
        "rating": rating,
        "foldcollect": "F",
        "tags": tags,
        "comment": comment,
        "private": private,
        "share_shuo": False,
    }
    if not apply:
        return {
            "subject_id": sid,
            "url": page_url,
            "dry_run": True,
            "before": before_interest,
            "planned": planned_payload,
            "apply_command": build_apply_command(sid, interest=interest, rating=rating, comment=comment, tags=tags, private=private),
            "gate": gate,
        }

    result = session.eval(
        f"""(async () => {{
          const sid = {json.dumps(sid)};
          const interest = {json.dumps(interest)};
          const rating = {json.dumps("" if rating is None else str(rating))};
          const comment = {json.dumps(comment)};
          const tags = {json.dumps(tags)};
          const isPrivate = {json.dumps(private)};
          const ck = (document.cookie.match(/(?:^|;\\s*)ck=([^;]+)/) || [])[1] || "";
          if (!ck) return JSON.stringify({{ok:false, code:"missing_ck", message:"Douban ck cookie is missing"}});
          const body = new URLSearchParams();
          body.append("ck", decodeURIComponent(ck.replace(/^\\\"|\\\"$/g, "")));
          body.append("interest", interest);
          body.append("rating", rating);
          body.append("foldcollect", "F");
          body.append("tags", tags);
          body.append("comment", comment);
          if (isPrivate) body.append("private", "on");
          body.append("save", "保存");
          const response = await fetch(`/j/subject/${{sid}}/interest`, {{
            method: "POST",
            credentials: "include",
            headers: {{
              "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
              "X-Requested-With": "XMLHttpRequest"
            }},
            body: body.toString()
          }});
          const text = await response.text();
          let parsed = null;
          try {{ parsed = JSON.parse(text); }} catch (error) {{}}
          return JSON.stringify({{
            ok: response.ok && parsed && parsed.r === 0,
            http_status: response.status,
            response: parsed,
            response_text_sample: parsed ? null : text.slice(0, 240)
          }});
        }})()"""
    )
    if not isinstance(result, dict):
        raise AgentError("mark_response_unreadable", "Could not read Douban mark response", exit_code=5, details={"result": result})
    if not result.get("ok"):
        raise AgentError(
            "mark_failed",
            "Douban interest API did not confirm success.",
            exit_code=7,
            details={"response": result, "before": before_interest, "page_url": page_url},
            next_actions=["Run `douban auth status`; if authenticated, rerun once. If it still fails, use --keep-tab and inspect the opened Edge page."],
        )

    session.navigate(url)
    after = read_interest_from_current_page(session, sid, command="mark verification")
    expected_marked = after.get("interest") == interest
    expected_rating = rating is None or after.get("my_rating") == rating
    if not expected_marked or not expected_rating:
        raise AgentError(
            "mark_verification_failed",
            "Douban API returned success but refreshed page did not show the expected state.",
            exit_code=7,
            details={
                "expected": {"interest": interest, "rating": rating},
                "actual": {"interest": after.get("interest"), "my_rating": after.get("my_rating")},
                "api_response": result.get("response"),
            },
            next_actions=["Open the movie page in Edge and inspect whether Douban delayed the update or changed its DOM."],
        )

    return {
        "subject_id": sid,
        "url": url,
        "dry_run": False,
        "before": before_interest,
        "after": after,
        "applied": planned_payload,
        "api_response": result.get("response"),
    }


def browser_mine(session: BrowserSession) -> dict[str, Any]:
    session.open("https://www.douban.com/mine/")
    info = session.info()
    uid = extract_uid_from_url(str(info.get("url") or ""))
    if not uid:
        return {
            "authenticated": False,
            "next_action": "Open Edge and log in to Douban, then rerun `douban mine`.",
        }
    return {
        "authenticated": True,
        "uid": "[REDACTED]",
        "profile_url": "https://www.douban.com/people/[REDACTED]/",
        "movie_urls": {
            "collect": "https://movie.douban.com/people/[REDACTED]/collect",
            "wish": "https://movie.douban.com/people/[REDACTED]/wish",
            "do": "https://movie.douban.com/people/[REDACTED]/do",
        },
    }


def run_with_browser(args: argparse.Namespace, fn: Any) -> Any:
    proxy = CdpProxy(args.cdp_base, args.timeout)
    with BrowserSession(proxy, keep_tab=args.keep_tab) as session:
        return fn(session)


def cmd_doctor(args: argparse.Namespace) -> dict[str, Any]:
    proxy = CdpProxy(args.cdp_base, args.timeout)
    health: dict[str, Any] | None = None
    targets_ok = False
    error: str | None = None
    try:
        health = proxy.health()
        proxy.targets()
        targets_ok = True
    except AgentError as exc:
        error = exc.message
    return {
        "cdp_base": args.cdp_base,
        "cdp_health": health,
        "targets_ok": targets_ok,
        "error": error,
        "next_action": None if targets_ok else "Run `agent-access doctor douban` or web-access check-deps.",
    }


def cmd_auth_status(args: argparse.Namespace) -> dict[str, Any]:
    return run_with_browser(args, browser_auth_status)


def cmd_auth_login(args: argparse.Namespace) -> dict[str, Any]:
    proxy = CdpProxy(args.cdp_base, args.timeout)
    session = BrowserSession(proxy, keep_tab=True)
    target_id = session.open(DOUBAN_LOGIN_URL)
    result = session.eval(
        r"""(() => JSON.stringify({
          title: document.title,
          url: location.href,
          text_sample: (document.body && document.body.innerText || "").replace(/\s+/g, " ").trim().slice(0, 240),
          has_qr: !!document.querySelector("canvas, img[src*='qr'], img[src*='qrcode'], .qrcode, .qr-code"),
          has_phone_input: !!document.querySelector("input[type='tel'], input[name*='phone'], input[name*='mobile']"),
          has_password_input: !!document.querySelector("input[type='password']")
        }))()"""
    )
    page = result if isinstance(result, dict) else {}
    gate = detect_douban_gate(str(page.get("url") or ""), str(page.get("text_sample") or ""))
    return {
        "method": "browser-session",
        "status": "login_tab_opened",
        "target_id": target_id,
        "login_url": DOUBAN_LOGIN_URL,
        "page_url": page.get("url") or DOUBAN_LOGIN_URL,
        "page_title": page.get("title"),
        "detected": {
            "qr": bool(page.get("has_qr")),
            "phone_input": bool(page.get("has_phone_input")),
            "password_input": bool(page.get("has_password_input")),
            "gate": gate,
        },
        "next_action": "Complete Douban login in the opened Edge tab, then run `douban auth status`.",
    }


def cmd_nowplaying(args: argparse.Namespace) -> dict[str, Any]:
    return run_with_browser(
        args,
        lambda session: browser_nowplaying(
            session,
            city=args.city,
            limit=args.limit,
            include_zero=args.include_zero,
        ),
    )


def parse_exclude_interest(value: str) -> set[str]:
    result: set[str] = set()
    for part in (value or "").split(","):
        item = part.strip()
        if not item:
            continue
        result.add(normalize_interest(item))
    return result


def cmd_recommend_nowplaying(args: argparse.Namespace) -> dict[str, Any]:
    exclude = parse_exclude_interest(args.exclude)
    return run_with_browser(
        args,
        lambda session: browser_recommend_nowplaying(
            session,
            city=args.city,
            limit=args.limit,
            include_zero=args.include_zero,
            exclude=exclude,
            new_only=bool(args.new_only),
            year=args.year,
        ),
    )


def cmd_search(args: argparse.Namespace) -> dict[str, Any]:
    return run_with_browser(args, lambda session: browser_search(session, query=args.query, limit=args.limit))


def cmd_movie(args: argparse.Namespace) -> dict[str, Any]:
    def run(session: BrowserSession) -> dict[str, Any]:
        resolved = resolve_subject(session, args.subject)
        data = browser_movie(session, resolved.subject_id)
        data["resolved_subject"] = resolved.to_dict()
        return data

    return run_with_browser(args, run)


def cmd_rating(args: argparse.Namespace) -> dict[str, Any]:
    def run(session: BrowserSession) -> dict[str, Any]:
        resolved = resolve_subject(session, args.subject)
        data = browser_movie(session, resolved.subject_id)
        return {
            "subject_id": data["subject_id"],
            "title": data["title"],
            "year": data["year"],
            "rating": data["rating"],
            "rating_people": data["rating_people"],
            "url": data["url"],
            "page_url": data["page_url"],
            "gate": data["gate"],
            "resolved_subject": resolved.to_dict(),
        }

    return run_with_browser(args, run)


def cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    def run(session: BrowserSession) -> dict[str, Any]:
        resolved = resolve_subject(session, args.subject)
        data = browser_interest(session, resolved.subject_id)
        data["resolved_subject"] = resolved.to_dict()
        return data

    return run_with_browser(args, run)


def cmd_mark(args: argparse.Namespace) -> dict[str, Any]:
    interest = normalize_interest(args.interest)
    rating = normalize_rating(args.rating)
    require_rating_interest_compatible(interest, rating)

    def run(session: BrowserSession) -> dict[str, Any]:
        resolved = resolve_subject(session, args.subject)
        data = browser_mark_interest(
            session,
            resolved.subject_id,
            interest=interest,
            rating=rating,
            comment=args.comment or "",
            tags=args.tags or "",
            private=bool(args.private),
            apply=bool(args.apply),
        )
        data["resolved_subject"] = resolved.to_dict()
        return data

    return run_with_browser(args, run)


def cmd_rate(args: argparse.Namespace) -> dict[str, Any]:
    rating = normalize_rating(args.rating)
    if rating is None:
        raise AgentError(
            "rating_required",
            "`douban rate` requires --rating 1..5.",
            exit_code=2,
            next_actions=["Example: douban rate 1292052 --rating 5 --apply"],
        )

    def run(session: BrowserSession) -> dict[str, Any]:
        resolved = resolve_subject(session, args.subject)
        data = browser_mark_interest(
            session,
            resolved.subject_id,
            interest="collect",
            rating=rating,
            comment=args.comment or "",
            tags=args.tags or "",
            private=bool(args.private),
            apply=bool(args.apply),
        )
        data["resolved_subject"] = resolved.to_dict()
        return data

    return run_with_browser(args, run)


def cmd_mine(args: argparse.Namespace) -> dict[str, Any]:
    return run_with_browser(args, browser_mine)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Agent-friendly Douban CLI. JSON output only.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--cdp-base", default=DEFAULT_CDP_BASE)
    parser.add_argument("--keep-tab", action="store_true", help="Keep the created Edge tab open for debugging.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Check Edge CDP connectivity.")

    auth = sub.add_parser("auth", help="Manage/check Douban browser-session auth.")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    auth_sub.add_parser("status", help="Check whether Edge is logged in to Douban.")
    auth_sub.add_parser("login", help="Return browser login instructions.")

    mine = sub.add_parser("mine", help="Show sanitized current Douban profile pointers.")
    mine.set_defaults(command="mine")

    nowplaying = sub.add_parser("nowplaying", help="List current city cinema movies.")
    nowplaying.add_argument("--city", default=DEFAULT_CITY)
    nowplaying.add_argument("--limit", type=int, default=10)
    nowplaying.add_argument("--include-zero", action="store_true", help="Include unrated movies with score 0.")

    recommend = sub.add_parser("recommend-nowplaying", help="Rank nowplaying movies, excluding already watched by default.")
    recommend.add_argument("--city", default=DEFAULT_CITY)
    recommend.add_argument("--limit", type=int, default=5)
    recommend.add_argument("--include-zero", action="store_true", help="Include unrated movies with score 0.")
    recommend.add_argument("--new-only", action="store_true", help="Only include movies whose release/year starts with the current year.")
    recommend.add_argument("--year", help="Only include movies whose release/year starts with YEAR, e.g. 2026.")
    recommend.add_argument(
        "--exclude",
        default="collect",
        help="Comma-separated interest states to exclude. Default: collect (看过).",
    )

    search = sub.add_parser("search", help="Search Douban movie subjects.")
    search.add_argument("query", help="Movie title or keyword.")
    search.add_argument("--limit", type=int, default=5)

    movie = sub.add_parser("movie", help="Read a movie subject summary.")
    movie.add_argument("subject", help="Subject id, movie URL, or title query.")

    rating = sub.add_parser("rating", help="Read a movie's Douban rating summary.")
    rating.add_argument("subject", help="Subject id, movie URL, or title query.")

    status = sub.add_parser("status", help="Read current user's interest status for a movie.")
    status.add_argument("subject", help="Subject id, movie URL, or title query.")

    mark = sub.add_parser("mark", help="Mark a movie as wish/collect/do. Dry-run by default; use --apply to write.")
    mark.add_argument("subject", help="Subject id, movie URL, or title query.")
    mark.add_argument("interest", help="wish/collect/do or 想看/看过/在看.")
    mark.add_argument("--rating", type=int, help="1..5 rating; only valid with collect/看过.")
    mark.add_argument("--comment", default="", help="Optional short comment.")
    mark.add_argument("--tags", default="", help="Optional comma-separated tags.")
    mark.add_argument("--private", action="store_true", help="Mark as private.")
    mark.add_argument("--apply", action="store_true", help="Actually write to Douban. Without this, returns a dry-run plan.")

    rate = sub.add_parser("rate", help="Convenience command: mark as collect/看过 with a rating. Dry-run by default.")
    rate.add_argument("subject", help="Subject id, movie URL, or title query.")
    rate.add_argument("--rating", type=int, required=True, help="1..5 rating. 1=很差, 5=力荐.")
    rate.add_argument("--comment", default="", help="Optional short comment.")
    rate.add_argument("--tags", default="", help="Optional comma-separated tags.")
    rate.add_argument("--private", action="store_true", help="Mark as private.")
    rate.add_argument("--apply", action="store_true", help="Actually write to Douban. Without this, returns a dry-run plan.")

    cities = sub.add_parser("cities", help="List built-in city aliases.")
    cities.set_defaults(command="cities")

    return parser


def dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "doctor":
        return json_envelope("doctor", cmd_doctor(args))
    if args.command == "auth":
        if args.auth_command == "status":
            return json_envelope("auth status", cmd_auth_status(args))
        if args.auth_command == "login":
            return json_envelope("auth login", cmd_auth_login(args))
    if args.command == "mine":
        return json_envelope("mine", cmd_mine(args))
    if args.command == "nowplaying":
        return json_envelope("nowplaying", cmd_nowplaying(args))
    if args.command == "recommend-nowplaying":
        return json_envelope("recommend-nowplaying", cmd_recommend_nowplaying(args))
    if args.command == "search":
        return json_envelope("search", cmd_search(args))
    if args.command == "movie":
        return json_envelope("movie", cmd_movie(args))
    if args.command == "rating":
        return json_envelope("rating", cmd_rating(args))
    if args.command == "status":
        return json_envelope("status", cmd_status(args))
    if args.command == "mark":
        return json_envelope("mark", cmd_mark(args))
    if args.command == "rate":
        return json_envelope("rate", cmd_rate(args))
    if args.command == "cities":
        return json_envelope("cities", {"aliases": CITY_ALIASES, "default": DEFAULT_CITY})
    raise AgentError("unknown_command", f"Unknown command: {args.command}", exit_code=2)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        write_json(dispatch(args))
        return 0
    except AgentError as exc:
        fail(exc)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
