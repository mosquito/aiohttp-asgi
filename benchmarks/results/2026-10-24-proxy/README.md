# FastAPI proxy results — 2026-10-24

[Method and interpretation](../../../docs/benchmarks.md#proxy-workloads).

13 configurations × 4 proxy workloads × 3 repeats, five seconds per sample,
100 connections and four workers. All 156 proxy samples and six upstream
controls passed response and counter checks. The incomplete Daphne run
and later uv environment checks are excluded.

CSV, JSON metadata and archives use Git LFS: run `git lfs pull`.
`source.tar.gz` contains the measured 839d04d code; `raw.tar.gz` contains
reports, per-request timings, logs, metadata and worker snapshots.
