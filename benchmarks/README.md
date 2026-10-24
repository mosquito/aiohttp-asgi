# FastAPI benchmarks

FastAPI validates data, calculates prices, returns JSON and proxies HTTP
through aiohttp/httpx with 1 KiB/64 KiB bodies. Echo is only the upstream
capacity control. [Method and results](../docs/benchmarks.md).

Run from the repository root on Linux with Python 3.13, uv, oha 1.16.0
and taskset. Four workers with proxy workloads need 13 CPUs and free ports
18080/18081.

```sh
uv sync --project benchmarks --frozen
uv run --project benchmarks --frozen pytest -q benchmarks
uv run --project benchmarks --frozen python -m benchmarks.run --workers 4 \
  --duration 5 --repeats 3 --concurrency 100 \
  --revision "$(git rev-parse HEAD)" --output /tmp/fastapi-bench
uv run --project benchmarks --frozen python -m benchmarks.summarize /tmp/fastapi-bench
uv run --project benchmarks --frozen python -m benchmarks.summarize /tmp/fastapi-bench/backend
```

The project has its own `pyproject.toml`, `uv.lock` and `.venv`; aiohttp-asgi
is an editable dependency on the parent directory. Use a new output directory.

Filter with `--servers aiohttp-asgi-rloop aiohttp-asgi-uvloop` or `--workloads`:

- REST: `get-item post-order` (needs 9 CPUs for four workers).
- Proxy: `proxy-aiohttp-1k proxy-httpx-1k proxy-aiohttp-64k proxy-httpx-64k`.

Daphne supports REST cases here; proxy cases require ASGI lifespan.
The runner checks JSON, sizes, statuses, worker affinity and request counters.
Reports include RPS, latency p50/p95/p99, approximate TTFB and raw client timings.
Saved CSV/JSON/archives use Git LFS: `git lfs pull` to fetch them.
