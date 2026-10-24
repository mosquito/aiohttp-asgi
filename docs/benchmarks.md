# Application benchmarks

`aiohttp-asgi` keeps aiohttp in the request path and adds an ASGI adapter.
An empty-response microbenchmark says little about an application using it.
This suite measures FastAPI doing validation, calculations, JSON responses
and outgoing HTTP requests—the work that users will actually run.

## Method

| Route | Work |
| --- | --- |
| GET `/items/42?quantity=3&currency=EUR` | Validate parameters, look up an item, calculate a quote, serialize JSON |
| POST `/orders` | Validate nested models, calculate prices/discount, serialize a receipt |
| POST `/proxy/aiohttp` | Forward a JSON body through a shared aiohttp client and return the upstream bytes |
| POST `/proxy/httpx` | The same operation through a shared httpx client |

The proxy cases use 1 KiB and 64 KiB data strings: **1,036 and 65,548 bytes**
including JSON syntax. They buffer both directions and do not reserialize JSON.
The REST routes use an in-memory catalog; there is no database or artificial delay.

- Same FastAPI application and native server CLIs; access logging disabled.
- HTTP/1.1 over loopback, 100 keep-alive connections, three five-second oha
  samples per case, each after a one-second warmup. Order is shuffled, seed 42.
- Four server workers share CPUs 1–4; the generator uses CPUs 12–15.
  The one-worker REST series uses CPU 1, with the same generator budget.
- Proxy upstream: four native aiohttp/uvloop echo processes on CPUs 5–8.
  Its direct capacity is checked only to control the upstream bottleneck.
- One shared outbound client of each kind per worker, created/closed in
  FastAPI lifespan. Both have a 100-connection pool, 30-second keep-alive idle
  timeout, no environment proxies, uncompressed bodies and five-second timeouts.
  aiohttp applies a total timeout; httpx applies per-phase timeouts. None fired.
- Exact JSON, response sizes, worker PIDs/loops/thread affinities and request
  counters are checked. Errors, non-200 responses or restarts reject a sample.

The Arch Linux VM has 16 vCPUs on a Ryzen AI 9 HX PRO 370 host. Versions:
CPython 3.13.16, FastAPI 0.162.0, Pydantic 2.14.1, aiohttp 3.14.5,
httpx 0.28.1, uvloop 0.23.0, rloop 0.5.0, oha 1.16.0.
Exact versions and commands are in the metadata.

The saved REST series has **102 samples**. The later proxy series has
**156 samples** across 13 configurations; its six upstream control samples
also passed. Daphne remains in the REST series but is excluded from proxy
cases because its CLI does not run ASGI lifespan for shared client sessions.
The initial incomplete proxy run is excluded from all tables.

Values below are medians of three samples. A median of sample p99 values
is not the p99 of all requests merged. Latencies are milliseconds.

## REST results

| Configuration | GET req/s | POST req/s | GET p99 | POST p99 |
| --- | ---: | ---: | ---: | ---: |
| aiohttp-asgi-rloop | 18,925 | 17,507 | 15.841 | 15.528 |
| aiohttp-asgi-uvloop | 18,813 | 17,241 | 12.387 | 13.382 |
| aiohttp-asgi-asyncio | 17,392 | 16,819 | 13.365 | 15.145 |
| anycorn | 7,378 | 6,607 | 33.946 | 37.231 |
| granian | 29,096 | 23,978 | 9.274 | 10.382 |
| granian-rloop | 30,311 | 24,526 | 8.962 | 9.188 |
| gunicorn-asgi | 21,891 | 20,366 | 10.99 | 11.118 |
| gunicorn-uvicorn | 24,780 | 23,900 | 9.907 | 10.368 |
| hypercorn-asyncio | 12,570 | 11,904 | 20.075 | 25.638 |
| hypercorn-uvloop | 12,910 | 12,106 | 17.089 | 18.229 |
| uvicorn-h11 | 2,397 | 2,402 | 47.064 | 46.971 |
| uvicorn-httptools | 24,256 | 24,017 | 9.565 | 9.754 |
| uvicorn-rloop | 24,322 | 24,123 | 10.228 | 9.357 |
| daphne | 13,439 | 11,438 | 27.685 | 28.931 |

These describe the complete FastAPI request path, not isolated adapter cost.
For this application, aiohttp-asgi/rloop achieves about 78% of Uvicorn/httptools
GET throughput and 73% of POST throughput. That is useful context for running
FastAPI alongside aiohttp handlers, rather than a claim to replace every server.

### Workers and event loops

| Loop | GET, 1 worker | GET, 4 workers | POST, 1 worker | POST, 4 workers |
| --- | ---: | ---: | ---: | ---: |
| rloop | 5,387 | 18,925 | 4,702 | 17,507 |
| uvloop | 5,508 | 18,813 | 4,637 | 17,241 |
| stdlib | 4,862 | 17,392 | 5,142 | 16,819 |

rloop and uvloop scale by about 3.4–3.7× here. With four workers, rloop's
median is only 0.6% ahead on GET and 1.5% on POST; sample ranges overlap.
uvloop has lower REST p99 on both routes. One worker also changes the ordering:
uvloop leads GET, stdlib leads POST. An empty-handler ranking would miss this.

## Proxy workloads

| Configuration | aiohttp 1k req/s | httpx 1k req/s | aiohttp 64k req/s | httpx 64k req/s |
| --- | ---: | ---: | ---: | ---: |
| aiohttp-asgi-rloop | 8,427 | 2,033 | 6,265 | 1,628 |
| aiohttp-asgi-uvloop | 9,324 | 2,343 | 6,460 | 1,839 |
| aiohttp-asgi-asyncio | 9,094 | 2,232 | 6,428 | 1,844 |
| anycorn | 4,659 | 1,719 | 3,311 | 1,269 |
| granian | 12,703 | 2,974 | 7,946 | 2,394 |
| granian-rloop | 12,778 | 2,521 | 7,543 | 2,056 |
| gunicorn-asgi | 10,410 | 2,393 | 7,021 | 2,128 |
| gunicorn-uvicorn | 11,523 | 2,596 | 7,718 | 2,147 |
| hypercorn-asyncio | 7,185 | 1,890 | 4,749 | 1,488 |
| hypercorn-uvloop | 7,446 | 2,297 | 5,361 | 1,609 |
| uvicorn-h11 | 2,333 | 1,541 | 6,072 | 1,706 |
| uvicorn-httptools | 12,263 | 2,448 | 8,068 | 1,934 |
| uvicorn-rloop | 11,147 | 1,853 | 7,483 | 1,669 |

Inside aiohttp-asgi, changing the outbound client changes median throughput
by **3.5–4.1×** in these buffered HTTP/1.1 cases. This is a larger effect
than changing the event loop. It is evidence about this application's HTTP
path, not a universal client-library ranking or an explanation of its internals.

The proxy workload also changes the loop comparison: uvloop has higher
median RPS than rloop in all four cases, and lower p99 with httpx. stdlib
is competitive. The configured default remains `rloop → uvloop → stdlib`;
these results support choosing a loop for the actual workload rather than
calling that priority a universal performance winner.

### Response latency

The aiohttp-asgi cases show why RPS alone is insufficient. Other configurations'
p50/p95/p99 are included in the CSV.

| Loop | Upstream client | Data | p50 | p95 | p99 |
| --- | --- | --- | ---: | ---: | ---: |
| rloop | aiohttp | 1k | 9.604 | 24.714 | 33.479 |
| rloop | httpx | 1k | 26.274 | 176.803 | 396.172 |
| rloop | aiohttp | 64k | 14.49 | 25.266 | 33.647 |
| rloop | httpx | 64k | 37.008 | 249.719 | 625.107 |
| uvloop | aiohttp | 1k | 9.289 | 20.553 | 31.537 |
| uvloop | httpx | 1k | 24.626 | 130.182 | 208.608 |
| uvloop | aiohttp | 64k | 14.098 | 24.91 | 37.865 |
| uvloop | httpx | 64k | 32.364 | 156.58 | 330.456 |
| stdlib | aiohttp | 1k | 9.574 | 21.125 | 27.757 |
| stdlib | httpx | 1k | 29.361 | 142.399 | 271.584 |
| stdlib | aiohttp | 64k | 13.322 | 31.588 | 41.523 |
| stdlib | httpx | 64k | 28.506 | 189.131 | 379.343 |

For rloop, the httpx cases reach p99 of about 396/625 ms, versus 33/34 ms
with aiohttp. These are saturated, closed-loop measurements at the same
concurrency, not latency at an equal independent request arrival rate.

### TTFB and body delivery

Each proxy sample also has a separate 1,000-request aiohttp probe at
concurrency 100 on a fixed stdlib client loop. It records parsed headers
as an **approximate TTFB/header-completion time**, first body, the per-request
headers-to-body gap and total response, each with p50/p95/p99 and raw JSONL.
These are client API observations, not packet timestamps or exact last-header timing.

| Configuration | Upstream client | Data | Headers p50 | Headers p95 | Headers p99 | Gap p50 |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| rloop | aiohttp | 1k | 14.904 | 50.953 | 66.757 | 0.002 |
| rloop | httpx | 1k | 3.303 | 766.497 | 1109.26 | 0.004 |
| rloop | aiohttp | 64k | 19.038 | 68.165 | 69.461 | 0.003 |
| rloop | httpx | 64k | 3.334 | 565.16 | 776.304 | 0.004 |
| uvicorn-h11 | aiohttp | 1k | 3.603 | 91.55 | 114.146 | 40.594 |
| uvicorn-h11 | aiohttp | 64k | 20.746 | 79.342 | 83.197 | 0.002 |

The proxy reads the complete upstream body before sending downstream headers,
so downstream TTFB includes that upstream transfer. The large httpx tail is
already present before parsed headers; the rloop median header-to-body gap
is only a few microseconds. Profiling is needed to assign the cost to a
particular client or scheduler component.

The h11 configuration shows a roughly 40 ms header-to-body gap with 1 KiB
bodies, which disappears with 64 KiB bodies. Its aiohttp-proxy throughput
therefore rises from about 2.3k to 6.1k req/s with the larger body. The cause
was not established; this is a configuration/payload observation, not a
statement about every h11 deployment. Its h11 case also uses asyncio,
while the httptools case uses uvloop.

The ordinary oha latency covers the full response. Its `firstBytePercentiles`
means the first body frame after header parsing, not the first HTTP byte.
The separate probe and oha have different request populations; their
percentiles must not be merged or subtracted to calculate a body gap.

### Body throughput

For aiohttp-asgi/rloop, increasing the data string from 1 to 64 KiB changes
one-direction body rate from **8.3 to 391.7 MiB/s** with aiohttp,
and **2.0 to 101.7 MiB/s** with httpx, despite lower RPS.
The calculation is `RPS × body bytes / 2**20`, excluding HTTP/TCP overhead.
A proxy transaction transfers request and response bodies over two hops.

The upstream control delivered 66.1k/34.4k req/s, over 5×/4× the highest
proxy medians for the two sizes. This gives headroom at the tested concurrency;
it does not prove that backend/kernel contention cannot affect tail latency.
Its control data is downloadable, not a separate benchmark conclusion.

## Limits

These are small application workloads on a shared VM. Three short runs
cannot establish small differences reliably. Loopback measures HTTP work,
scheduling and buffer handling in one kernel, not physical NIC capacity or
WAN latency. There is no TLS, streaming, connection churn, remote database,
WebSocket/HTTP2/3 or long-running stability test. Saturated p99 is not a production SLO.

## Run and inspect

Run from the repository root on Linux with oha, taskset and at least 13 CPUs
for four workers. Ports 18080/18081 must be free.

```sh
uv sync --project benchmarks --frozen
uv run --project benchmarks --frozen pytest -q benchmarks
uv run --project benchmarks --frozen python -m benchmarks.run --workers 4 \
  --duration 5 --repeats 3 --concurrency 100 \
  --revision "$(git rev-parse HEAD)" --output /tmp/fastapi-bench
uv run --project benchmarks --frozen python -m benchmarks.summarize /tmp/fastapi-bench
```

The benchmark has its own `pyproject.toml`, `uv.lock` and `.venv`, with
an editable dependency on the repository package. `--workloads` and
`--servers` select subsets. Use a new output directory each time.

Artifacts use Git LFS: run `git lfs pull` after cloning. The REST and proxy
series were captured in separate runs and retain their exact source/metadata;
the proxy snapshot is the measured `839d04d` code before history cleanup.
The current uv lock preserves the measured HTTP-stack versions.

- REST: {download}`workers=1 CSV <../benchmarks/results/2026-10-24-fastapi/workers1.csv>`,
  {download}`workers=4 CSV <../benchmarks/results/2026-10-24-fastapi/workers4.csv>`,
  {download}`metadata=1 <../benchmarks/results/2026-10-24-fastapi/metadata-workers1.json>`,
  {download}`metadata=4 <../benchmarks/results/2026-10-24-fastapi/metadata-workers4.json>`,
  {download}`source <../benchmarks/results/2026-10-24-fastapi/source.tar.gz>`,
  {download}`raw reports <../benchmarks/results/2026-10-24-fastapi/raw.tar.gz>`.
- Proxy: {download}`CSV <../benchmarks/results/2026-10-24-proxy/workers4.csv>`,
  {download}`metadata <../benchmarks/results/2026-10-24-proxy/metadata.json>`,
  {download}`source <../benchmarks/results/2026-10-24-proxy/source.tar.gz>`,
  {download}`raw reports and client timings <../benchmarks/results/2026-10-24-proxy/raw.tar.gz>`.
- Upstream control: {download}`CSV <../benchmarks/results/2026-10-24-proxy/backend.csv>`,
  {download}`metadata <../benchmarks/results/2026-10-24-proxy/metadata-backend.json>`.
