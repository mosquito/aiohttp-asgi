# FastAPI CLI comparison — 2026-10-24

FastAPI 0.162.0, Pydantic 2.14.1, CPython 3.13.16, aiohttp 3.14.5,
rloop 0.5.0, uvloop 0.23.0, oha 1.16.0. Arch Linux VM with 16 vCPUs
on an AMD Ryzen AI 9 HX PRO 370 host; Linux 7.2.11-arch1-1.

All servers run the same FastAPI REST example through their real CLI.
GET validates path/query parameters, looks up a catalog item and returns
a typed quote. POST validates nested order lines and serializes a typed
receipt after calculating prices and a discount. The catalog is read-only;
no database or artificial delay is used. See [methodology](../../README.md).

100 keep-alive connections, HTTP/1.1 over loopback, access logging disabled.
Server CPU affinity: CPU 1 with one worker, CPUs 1–4 with four workers.
The client always uses CPUs 12–15. Each case has three five-second samples
and a one-second warmup before each sample; order is shuffled with seed 42.

All 102 main samples passed exact JSON checks, response-size validation
and request accounting. Every measured HTTP 200 response matched one
application request in the sum of the worker counters. Worker PID, event
loop and per-thread CPU affinity were verified. Startup, diagnostics and
warmup are excluded from measured counter deltas.

## aiohttp-asgi event loops

Values are medians in requests/second.

| Loop | GET, 1 worker | GET, 4 workers | POST, 1 worker | POST, 4 workers |
| --- | ---: | ---: | ---: | ---: |
| rloop | 5,387 | 18,925 | 4,702 | 17,507 |
| uvloop | 5,508 | 18,813 | 4,637 | 17,241 |
| stdlib | 4,862 | 17,392 | 5,142 | 16,819 |

At four workers rloop is 0.6% above uvloop for GET and 1.5% for POST.
The per-run ranges overlap; this is not evidence of a large or universal
performance advantage. Both show roughly 3.4–3.7× scaling from one to four
workers in these workloads.

The configured default preference is rloop, then uvloop, then stdlib.
Only installed optional loops appear in CLI choices. Every benchmark
selects the loop explicitly, so the default-priority update does not
change these comparisons.

## Four workers across servers

All values are medians. Body-first and full latency refer to the GET case.

| Configuration | GET req/s | POST req/s | First body p99 ms | Full response p99 ms |
| --- | ---: | ---: | ---: | ---: |
| granian-rloop | 30,311 | 24,526 | 8.962 | 8.962 |
| granian | 29,096 | 23,978 | 9.273 | 9.274 |
| gunicorn-uvicorn | 24,780 | 23,900 | 9.906 | 9.907 |
| uvicorn-rloop | 24,322 | 24,123 | 10.227 | 10.228 |
| uvicorn-httptools | 24,256 | 24,017 | 9.564 | 9.565 |
| gunicorn-asgi | 21,891 | 20,366 | 10.989 | 10.990 |
| aiohttp-asgi-rloop | 18,925 | 17,507 | 15.841 | 15.841 |
| aiohttp-asgi-uvloop | 18,813 | 17,241 | 12.387 | 12.387 |
| aiohttp-asgi-asyncio | 17,392 | 16,819 | 13.365 | 13.365 |
| daphne | 13,439 | 11,438 | 27.684 | 27.685 |
| hypercorn-uvloop | 12,910 | 12,106 | 17.089 | 17.089 |
| hypercorn-asyncio | 12,570 | 11,904 | 20.073 | 20.075 |
| anycorn | 7,378 | 6,607 | 33.944 | 33.946 |
| uvicorn-h11 | 2,397 | 2,402 | 47.064 | 47.064 |

## Timing semantics and the h11 result

The ordinary p50/p99 columns measure receipt of the entire response.
In [oha 1.16.0](https://github.com/hatoo/oha/blob/v1.16.0/src/client.rs),
`firstBytePercentiles` is sampled when the first body frame becomes
available after parsing headers. It measures time to first body data,
not the first HTTP response byte. TTLH/header completion and the gap from
headers to body are not measured separately. These timing columns were
extracted from saved raw results without rerunning the workloads.

Uvicorn h11/asyncio with four workers shows an unusual repeatable ~41 ms
median latency and ~2.4k req/s on both routes. A separate one-worker
check gave ~4.9k GET and ~4.0k POST req/s. The cause was not established;
do not treat this configuration-specific anomaly as a general statement
about h11 performance. Its raw reports are retained in the archive.

## Reproducibility and limits

The baseline is commit `ebf66a5` plus the workers/event-loop runner changes
contained in [the exact measured source snapshot](source.tar.gz). The
snapshot was saved before starting the main matrix; later source edits
were not mixed into it. All loops were selected explicitly.

- [One-worker CSV, including ranges and latency percentiles](workers1.csv)
- [Four-worker CSV, including ranges and latency percentiles](workers4.csv)
- [One-worker environment and CLI commands](metadata-workers1.json)
- [Four-worker environment and CLI commands](metadata-workers4.json)
- [Raw reports, worker snapshots, logs and h11 check](raw.tar.gz)

The raw archive contains `workers1/`, `workers4/` and `h11-check/`.
Only the two main matrices contribute to the tables above. Earlier
incomplete/rejected runs are excluded.

These are short closed-loop measurements on a VM. Hypervisor scheduling
and client behavior affect throughput; physical cores are not reserved.
There is no external database, TLS, WebSocket, HTTP/2/3, connection-churn
or long-running stability measurement. Saturated p99 values are not an
open-loop latency SLO. Medians of sample percentiles are not percentiles
of a merged latency distribution.
