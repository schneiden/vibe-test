"""Tiny stdlib HTTP client for the i-urls affiliate API.

Kept dependency-free so the tests can run in CI without installing requests.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable

BASE_URL = "https://s-api.aff.i-urls.com"
DEFAULT_TIMEOUT = 15.0


@dataclass
class ApiResponse:
    status: int
    body: Any
    raw: str
    elapsed_ms: float
    url: str


def _build_url(path: str, query: dict[str, Any] | None) -> str:
    url = f"{BASE_URL}{path}"
    if query:
        clean = {k: v for k, v in query.items() if v is not None and v != ""}
        if clean:
            url = f"{url}?{urllib.parse.urlencode(clean)}"
    return url


def get_json(path: str, query: dict[str, Any] | None = None, timeout: float = DEFAULT_TIMEOUT) -> ApiResponse:
    import time

    url = _build_url(path, query)
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "vibe-test-api-check/1.0"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        status = e.code
    elapsed_ms = (time.perf_counter() - started) * 1000

    try:
        body = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        body = None
    return ApiResponse(status=status, body=body, raw=raw, elapsed_ms=elapsed_ms, url=url)


# Endpoints under test.

def cate_items(t_provider: str, category_id: str, mod: str | None = None, info: str | None = None, **extra: Any) -> ApiResponse:
    path = f"/api/v1/{urllib.parse.quote(t_provider)}/cate_items/{urllib.parse.quote(str(category_id))}"
    query: dict[str, Any] = {"mod": mod, "info": info}
    query.update(extra)
    return get_json(path, query)


def hot_items(t_provider: str, mod: str | None = None, info: str | None = None, **extra: Any) -> ApiResponse:
    path = f"/api/v1/{urllib.parse.quote(t_provider)}/hot_items"
    query: dict[str, Any] = {"mod": mod, "info": info}
    query.update(extra)
    return get_json(path, query)


# --- Response shape helpers ---------------------------------------------------

ITEM_LIST_KEYS = ("items", "data", "results", "list", "products")


def extract_items(body: Any) -> list[Any] | None:
    """Find the items list inside a response. Returns None if no list-like payload found."""
    if body is None:
        return None
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in ITEM_LIST_KEYS:
            value = body.get(key)
            if isinstance(value, list):
                return value
        # Some APIs nest under data.items
        nested = body.get("data")
        if isinstance(nested, dict):
            for key in ITEM_LIST_KEYS:
                value = nested.get(key)
                if isinstance(value, list):
                    return value
    return None


def is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    if isinstance(value, (list, dict, tuple, set)) and len(value) == 0:
        return True
    return False


def item_non_empty_field_count(item: Any) -> int:
    if not isinstance(item, dict):
        return 0 if is_empty_value(item) else 1
    return sum(1 for v in item.values() if not is_empty_value(v))


def summarize_items(items: Iterable[Any]) -> dict[str, Any]:
    items = list(items)
    total = len(items)
    empty_items = sum(1 for it in items if item_non_empty_field_count(it) == 0)
    avg_fields = (
        sum(item_non_empty_field_count(it) for it in items) / total if total else 0.0
    )
    return {"total": total, "empty_items": empty_items, "avg_non_empty_fields": avg_fields}
