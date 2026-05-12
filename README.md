# vibe-test

## API tests for the i-urls affiliate API

Automated checks for the two endpoints documented under 首頁和分類頁API:

- `GET /api/v1/{t_provider}/cate_items/{category_id}` — Cate Items Endpoint
- `GET /api/v1/{t_provider}/hot_items` — Hot Items Endpoint

The tests verify that the endpoints respond `200`, return a list-shaped payload,
and that the items carry real data (i.e. the API is **not** consistently
"吐空值"). Each endpoint is also hit several times to catch intermittent empty
responses.

Environments:

| env | base URL |
| --- | --- |
| stage | `https://s-api.aff.i-urls.com` (default) |
| production | `https://api.aff.i-urls.com` |

Docs: `https://s-api.aff.i-urls.com/docs#`

### Authentication

The API rejects unauthenticated calls with `401 MISSING_API_KEY`, so you must
supply a key via `VIBE_API_KEY`:

```bash
# stage
export VIBE_API_KEY="<stage api key>"

# production
export VIBE_BASE_URL="https://api.aff.i-urls.com"
export VIBE_API_KEY="<production api key>"
```

How the key is transmitted is **auto-detected**: before the tests run, the
client tries the known schemes (`X-API-Key` header, `Authorization: Bearer …`,
`?api_key=…`, etc.) against a live endpoint and pins the first one that isn't
rejected. If you already know the scheme, set it explicitly to skip detection:

```bash
export VIBE_API_AUTH_SCHEME="x-api-key"        # one of the known scheme names
# or force a custom header / query param:
export VIBE_API_KEY_HEADER="Authorization"
export VIBE_API_KEY_PARAM="api_key"
```

Without `VIBE_API_KEY`, the pytest suite is **skipped** (not failed).

### Run as pytest

```bash
pip3 install -r requirements-dev.txt
export VIBE_API_KEY="<api key>"
python3 -m pytest tests/ -v
```

Configurable via env vars:

| var | default | meaning |
| --- | --- | --- |
| `VIBE_API_KEY` | _(unset)_ | API key; required, suite is skipped without it |
| `VIBE_API_AUTH_SCHEME` | `auto` | force an auth scheme name instead of auto-detecting |
| `VIBE_API_KEY_HEADER` | _(unset)_ | force the key into this request header |
| `VIBE_API_KEY_PARAM` | _(unset)_ | force the key into this query-string param |
| `VIBE_BASE_URL` | `https://s-api.aff.i-urls.com` | API base URL (stage vs. production) |
| `VIBE_T_PROVIDER` | `yauc` | `t_provider` path segment |
| `VIBE_CATEGORY_IDS` | `2092101503,24698,18028718,2092096354` | comma-separated `category_id`s for `cate_items` |
| `VIBE_RUNS` | `3` | sequential calls per endpoint for the flake-detection tests |

### Run as a one-shot probe

```bash
export VIBE_API_KEY="<api key>"
python3 -m tests.test_api --runs 5 --category 2092101503
```

Prints the detected auth scheme and a per-run line like:

```
auth scheme detected: x-api-key (header X-API-Key)
[OK] cate_items[2092101503] run 1/5 http=200 elapsed=420ms items=20 empty_items=0 avg_fields=8.40
```

Exits non-zero if any run returns non-200, an empty list, or a list whose
items are all empty.
