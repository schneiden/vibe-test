"""Automated checks for the i-urls affiliate API.

Verifies that the two endpoints documented in 首頁和分類頁API:
    GET /api/v1/{t_provider}/cate_items/{category_id}
    GET /api/v1/{t_provider}/hot_items

return real, non-empty payloads (i.e. not consistently empty values).

Run with pytest:
    pytest tests/

Or run as a script for a polled health-check:
    python -m tests.test_api --runs 5 --category 2084261179
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any

import pytest

from tests.api_client import (
    ApiResponse,
    cate_items,
    detect_auth_scheme,
    extract_items,
    has_api_key,
    hot_items,
    item_non_empty_field_count,
    summarize_items,
)

# The endpoints require an API key (401 MISSING_API_KEY otherwise).
# Set VIBE_API_KEY before running, or these tests are skipped.
pytestmark = pytest.mark.skipif(
    not has_api_key(),
    reason="set VIBE_API_KEY (stage/prod key) to run the live API tests; see README",
)


@pytest.fixture(scope="session", autouse=True)
def _auth() -> None:
    """Figure out (once) how the API wants the key sent, before any test runs."""
    if not has_api_key():
        return
    scheme = detect_auth_scheme()
    if scheme is None:
        pytest.fail(
            "VIBE_API_KEY is set but every known auth scheme was rejected (401/403). "
            "Set VIBE_API_AUTH_SCHEME / VIBE_API_KEY_HEADER / VIBE_API_KEY_PARAM explicitly."
        )

T_PROVIDER = os.environ.get("VIBE_T_PROVIDER", "yauc")

# Real Yahoo!オークション category IDs that carry inventory (from the products DB).
# Override via VIBE_CATEGORY_IDS if needed.
DEFAULT_CATEGORY_IDS = os.environ.get(
    "VIBE_CATEGORY_IDS", "2092101503,24698,18028718,2092096354"
).split(",")

# How many sequential calls to make per endpoint when checking for "always empty" regressions.
RUNS_PER_ENDPOINT = int(os.environ.get("VIBE_RUNS", "3"))

# Minimum acceptable non-empty fields per item. Real listings carry title/url/image/price etc.
MIN_NON_EMPTY_FIELDS_PER_ITEM = 3


# --- assertion helpers -------------------------------------------------------

def _assert_ok(resp: ApiResponse, label: str) -> list[Any]:
    if resp.status == 401:
        pytest.fail(
            f"{label}: HTTP 401 — API key missing or wrong. "
            f"Check VIBE_API_KEY / VIBE_API_KEY_HEADER / VIBE_API_KEY_PARAM. body: {resp.raw[:300]}"
        )
    assert resp.status == 200, (
        f"{label}: HTTP {resp.status} from {resp.url}\nbody: {resp.raw[:500]}"
    )
    assert resp.body is not None, f"{label}: response was not JSON. body: {resp.raw[:500]}"
    items = extract_items(resp.body)
    assert items is not None, (
        f"{label}: could not locate an items list in response. "
        f"top-level type={type(resp.body).__name__}, keys="
        f"{list(resp.body.keys()) if isinstance(resp.body, dict) else 'n/a'}"
    )
    return items


def _assert_non_empty(items: list[Any], label: str) -> None:
    assert len(items) > 0, f"{label}: items list is empty (吐空值)"
    summary = summarize_items(items)
    assert summary["empty_items"] < summary["total"], (
        f"{label}: every item is empty/null. summary={summary}"
    )
    assert summary["avg_non_empty_fields"] >= MIN_NON_EMPTY_FIELDS_PER_ITEM, (
        f"{label}: items have too few populated fields "
        f"(avg={summary['avg_non_empty_fields']:.2f} < {MIN_NON_EMPTY_FIELDS_PER_ITEM}). "
        f"summary={summary}"
    )


# --- pytest cases ------------------------------------------------------------

@pytest.mark.parametrize("category_id", DEFAULT_CATEGORY_IDS)
def test_cate_items_returns_populated_list(category_id: str) -> None:
    resp = cate_items(T_PROVIDER, category_id)
    items = _assert_ok(resp, f"cate_items[{category_id}]")
    _assert_non_empty(items, f"cate_items[{category_id}]")


def test_hot_items_returns_populated_list() -> None:
    resp = hot_items(T_PROVIDER)
    items = _assert_ok(resp, "hot_items")
    _assert_non_empty(items, "hot_items")


@pytest.mark.parametrize("category_id", DEFAULT_CATEGORY_IDS[:1])
def test_cate_items_is_not_intermittently_empty(category_id: str) -> None:
    """Hits the endpoint several times to catch flakiness / intermittent empty payloads."""
    empty_runs = 0
    last_summary: dict[str, Any] | None = None
    for i in range(RUNS_PER_ENDPOINT):
        resp = cate_items(T_PROVIDER, category_id)
        items = _assert_ok(resp, f"cate_items[{category_id}] run {i + 1}")
        last_summary = summarize_items(items)
        if last_summary["total"] == 0 or last_summary["empty_items"] == last_summary["total"]:
            empty_runs += 1
        time.sleep(0.3)
    assert empty_runs == 0, (
        f"cate_items[{category_id}]: {empty_runs}/{RUNS_PER_ENDPOINT} runs returned empty. "
        f"last_summary={last_summary}"
    )


def test_hot_items_is_not_intermittently_empty() -> None:
    empty_runs = 0
    last_summary: dict[str, Any] | None = None
    for i in range(RUNS_PER_ENDPOINT):
        resp = hot_items(T_PROVIDER)
        items = _assert_ok(resp, f"hot_items run {i + 1}")
        last_summary = summarize_items(items)
        if last_summary["total"] == 0 or last_summary["empty_items"] == last_summary["total"]:
            empty_runs += 1
        time.sleep(0.3)
    assert empty_runs == 0, (
        f"hot_items: {empty_runs}/{RUNS_PER_ENDPOINT} runs returned empty. "
        f"last_summary={last_summary}"
    )


def test_optional_query_params_are_echoed() -> None:
    """mod and info are documented as optional pass-through params; the API should still 200."""
    resp = hot_items(T_PROVIDER, mod="item", info="loc1")
    _assert_ok(resp, "hot_items?mod=item&info=loc1")


# --- standalone runner -------------------------------------------------------

def _print_run(label: str, resp: ApiResponse, show_body_on_fail: bool = True, body_chars: int = 800) -> dict[str, Any]:
    items = extract_items(resp.body) or []
    summary = summarize_items(items)
    if resp.status == 401:
        status_word = "AUTH (401, set VIBE_API_KEY)"
        ok = False
    elif resp.status == 200 and summary["total"] > 0 and summary["empty_items"] < summary["total"]:
        status_word = "OK"
        ok = True
    else:
        status_word = "EMPTY/FAIL"
        ok = False
    print(
        f"[{status_word}] {label} "
        f"http={resp.status} elapsed={resp.elapsed_ms:.0f}ms "
        f"items={summary['total']} empty_items={summary['empty_items']} "
        f"avg_fields={summary['avg_non_empty_fields']:.2f}"
    )
    if not ok and show_body_on_fail:
        body_preview = resp.raw[:body_chars] if resp.raw else "(empty body)"
        print(f"    url:  {resp.url}")
        print(f"    body: {body_preview}")
        if isinstance(resp.body, dict):
            print(f"    top-level keys: {list(resp.body.keys())}")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe the i-urls cate_items / hot_items endpoints.")
    parser.add_argument("--provider", default=T_PROVIDER, help="t_provider value (default: yauc)")
    parser.add_argument(
        "--category",
        action="append",
        help="category_id to query for cate_items. Pass multiple times for multiple ids.",
    )
    parser.add_argument("--runs", type=int, default=RUNS_PER_ENDPOINT, help="runs per endpoint")
    parser.add_argument("--sleep", type=float, default=0.3, help="seconds between runs")
    args = parser.parse_args(argv)

    from tests import api_client

    categories = args.category or DEFAULT_CATEGORY_IDS
    print(f"base_url={api_client.BASE_URL} provider={args.provider} categories={categories} runs={args.runs}")
    if not api_client.has_api_key():
        print(
            "WARNING: VIBE_API_KEY is not set — the API will return 401 MISSING_API_KEY. "
            "Export it first, e.g.  export VIBE_API_KEY=xxxx"
        )
    else:
        scheme = api_client.detect_auth_scheme(f"/api/v1/{args.provider}/hot_items")
        if scheme is None:
            print("ERROR: API key set but no known auth scheme was accepted (all returned 401/403).")
            return 2
        print(f"auth scheme detected: {scheme.name} "
              f"({'header ' + scheme.header if scheme.header else 'query param ' + str(scheme.param)})")

    failures = 0
    for cat in categories:
        for i in range(args.runs):
            resp = cate_items(args.provider, cat)
            summary = _print_run(f"cate_items[{cat}] run {i + 1}/{args.runs}", resp)
            if resp.status != 200 or summary["total"] == 0 or summary["empty_items"] == summary["total"]:
                failures += 1
            time.sleep(args.sleep)

    for i in range(args.runs):
        resp = hot_items(args.provider)
        summary = _print_run(f"hot_items run {i + 1}/{args.runs}", resp)
        if resp.status != 200 or summary["total"] == 0 or summary["empty_items"] == summary["total"]:
            failures += 1
        time.sleep(args.sleep)

    print(f"\nfailures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
