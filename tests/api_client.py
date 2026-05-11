"""Tiny stdlib HTTP client for the i-urls affiliate API.

Kept dependency-free so the tests can run in CI without installing requests.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable

# stage:      https://s-api.aff.i-urls.com
# production: https://api.aff.i-urls.com
BASE_URL = os.environ.get("VIBE_BASE_URL", "https://s-api.aff.i-urls.com").rstrip("/")
DEFAULT_TIMEOUT = 15.0

# The API rejects unauthenticated calls with 401 MISSING_API_KEY.
# Provide the key via VIBE_API_KEY.
API_KEY = os.environ.get("VIBE_API_KEY", "").strip()

# How the key is transmitted. Pick one of the named schemes below via
# VIBE_API_AUTH_SCHEME, or force a custom header / query param:
#   VIBE_API_KEY_HEADER=Some-Header
#   VIBE_API_KEY_PARAM=some_param
# If none is set, "auto" tries the known schemes until one returns non-401.
AUTH_SCHEME = os.environ.get("VIBE_API_AUTH_SCHEME", "auto").strip().lower()
_CUSTOM_HEADER = os.environ.get("VIBE_API_KEY_HEADER", "").strip()
_CUSTOM_PARAM = os.environ.get("VIBE_API_KEY_PARAM", "").strip()


@dataclass
class AuthScheme:
    name: str
    header: str | None = None        # header name; value = api key
    header_prefix: str = ""          # e.g. "Bearer "
    param: str | None = None         # query-string param name; value = api key

    def headers(self, api_key: str) -> dict[str, str]:
        if self.header:
            return {self.header: f"{self.header_prefix}{api_key}"}
        return {}

    def query(self, api_key: str) -> dict[str, str]:
        if self.param:
            return {self.param: api_key}
        return {}


# Order matters: most-likely schemes first.
KNOWN_SCHEMES: list[AuthScheme] = [
    AuthScheme("x-api-key", header="X-API-Key"),
    AuthScheme("apikey-header", header="apikey"),
    AuthScheme("api-key-header", header="api-key"),
    AuthScheme("authorization-bearer", header="Authorization", header_prefix="Bearer "),
    AuthScheme("authorization-raw", header="Authorization"),
    AuthScheme("x-access-token", header="X-Access-Token"),
    AuthScheme("query-api_key", param="api_key"),
    AuthScheme("query-apikey", param="apikey"),
    AuthScheme("query-key", param="key"),
    AuthScheme("query-token", param="token"),
    AuthScheme("query-access_token", param="access_token"),
]


def _initial_scheme() -> AuthScheme:
    if _CUSTOM_HEADER:
        return AuthScheme("custom-header", header=_CUSTOM_HEADER)
    if _CUSTOM_PARAM:
        return AuthScheme("custom-param", param=_CUSTOM_PARAM)
    for s in KNOWN_SCHEMES:
        if s.name == AUTH_SCHEME:
            return s
    return KNOWN_SCHEMES[0]


# The scheme actually used for requests. Mutable so detect_auth_scheme() can pin it.
ACTIVE_SCHEME: AuthScheme = _initial_scheme()


def has_api_key() -> bool:
    return bool(API_KEY)


@dataclass
class ApiResponse:
    status: int
    body: Any
    raw: str
    elapsed_ms: float
    url: str


def _do_get(url: str, headers: dict[str, str], timeout: float) -> ApiResponse:
    import time

    base_headers = {"Accept": "application/json", "User-Agent": "vibe-test-api-check/1.0"}
    base_headers.update(headers)
    req = urllib.request.Request(url, headers=base_headers)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        status = e.code
    except urllib.error.URLError as e:
        return ApiResponse(status=0, body=None, raw=f"URLError: {e}", elapsed_ms=0.0, url=url)
    elapsed_ms = (time.perf_counter() - started) * 1000
    try:
        body = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        body = None
    return ApiResponse(status=status, body=body, raw=raw, elapsed_ms=elapsed_ms, url=url)


def get_json(
    path: str,
    query: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    scheme: AuthScheme | None = None,
) -> ApiResponse:
    scheme = scheme or ACTIVE_SCHEME
    merged: dict[str, Any] = dict(query or {})
    if API_KEY:
        merged.update(scheme.query(API_KEY))
    clean = {k: v for k, v in merged.items() if v is not None and v != ""}
    url = f"{BASE_URL}{path}"
    if clean:
        url = f"{url}?{urllib.parse.urlencode(clean)}"
    headers = scheme.headers(API_KEY) if API_KEY else {}
    return _do_get(url, headers, timeout)


def detect_auth_scheme(probe_path: str = "/api/v1/yauc/hot_items") -> AuthScheme | None:
    """Try the known auth schemes against a real endpoint; pin and return the first that isn't 401.

    Returns None if the key is missing or every scheme is rejected.
    """
    global ACTIVE_SCHEME
    if not API_KEY:
        return None
    candidates = [ACTIVE_SCHEME] + [s for s in KNOWN_SCHEMES if s.name != ACTIVE_SCHEME.name]
    for scheme in candidates:
        resp = get_json(probe_path, scheme=scheme)
        if resp.status not in (401, 403, 0):
            ACTIVE_SCHEME = scheme
            return scheme
    return None


# --- Endpoints under test ----------------------------------------------------

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


# --- Response shape helpers --------------------------------------------------

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
