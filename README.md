# vibe-test

## API tests for `s-api.aff.i-urls.com`

Automated checks for the two endpoints documented under 首頁和分類頁API:

- `GET /api/v1/{t_provider}/cate_items/{category_id}` — Cate Items Endpoint
- `GET /api/v1/{t_provider}/hot_items` — Hot Items Endpoint

The tests verify that the endpoints respond `200`, return a list-shaped payload,
and that the items carry real data (i.e. the API is **not** consistently
"吐空值"). Each endpoint is also hit several times to catch intermittent empty
responses.

### Run as pytest

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

Configurable via env vars:

| var | default | meaning |
| --- | --- | --- |
| `VIBE_T_PROVIDER` | `yauc` | `t_provider` path segment |
| `VIBE_CATEGORY_IDS` | `2084261179,2084032596,2084046530` | comma-separated `category_id`s for `cate_items` |
| `VIBE_RUNS` | `3` | sequential calls per endpoint for the flake-detection tests |

### Run as a one-shot probe

```bash
python -m tests.test_api --runs 5 --category 2084261179
```

Prints a per-run line like:

```
[OK] cate_items[2084261179] run 1/5 http=200 elapsed=420ms items=20 empty_items=0 avg_fields=8.40
```

Exits non-zero if any run returns `non-200`, an empty list, or a list whose
items are all empty.
