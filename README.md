# vibe-test

## API tests for `s-api.aff.i-urls.com`

Automated checks for the two endpoints documented under 首頁和分類頁API:

- `GET /api/v1/{t_provider}/cate_items/{category_id}` — Cate Items Endpoint
- `GET /api/v1/{t_provider}/hot_items` — Hot Items Endpoint

The tests verify that the endpoints respond `200`, return a list-shaped payload,
and that the items carry real data (i.e. the API is **not** consistently
"吐空值"). Each endpoint is also hit several times to catch intermittent empty
responses.

### Authentication

The API rejects unauthenticated calls with `401 MISSING_API_KEY`, so you must
supply a key:

```bash
export VIBE_API_KEY="your-key-here"
```

By default the key is sent as the `X-API-Key` request header. If the API expects
a different header name or a query-string parameter, override it:

```bash
export VIBE_API_KEY_HEADER="Authorization"   # e.g. send "Authorization: <key>"
# or
export VIBE_API_KEY_PARAM="api_key"          # send ?api_key=<key> instead of a header
```

Without `VIBE_API_KEY`, the pytest suite is **skipped** (not failed).

### Run as pytest

```bash
pip3 install -r requirements-dev.txt
export VIBE_API_KEY="your-key-here"
python3 -m pytest tests/ -v
```

Configurable via env vars:

| var | default | meaning |
| --- | --- | --- |
| `VIBE_API_KEY` | _(unset)_ | API key; required, suite is skipped without it |
| `VIBE_API_KEY_HEADER` | `X-API-Key` | header name the key is sent in |
| `VIBE_API_KEY_PARAM` | _(unset)_ | if set, send the key as this query param instead of a header |
| `VIBE_T_PROVIDER` | `yauc` | `t_provider` path segment |
| `VIBE_CATEGORY_IDS` | `2084261179,2084032596,2084046530` | comma-separated `category_id`s for `cate_items` |
| `VIBE_RUNS` | `3` | sequential calls per endpoint for the flake-detection tests |
| `VIBE_BASE_URL` | `https://s-api.aff.i-urls.com` | API base URL |

### Run as a one-shot probe

```bash
export VIBE_API_KEY="your-key-here"
python3 -m tests.test_api --runs 5 --category 2084261179
```

Prints a per-run line like:

```
[OK] cate_items[2084261179] run 1/5 http=200 elapsed=420ms items=20 empty_items=0 avg_fields=8.40
```

Exits non-zero if any run returns `non-200`, an empty list, or a list whose
items are all empty.
