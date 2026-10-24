"""Comparable aiohttp timings; TTFB is approximated by parsed headers."""

import asyncio
import json
import os
from statistics import quantiles
from time import perf_counter

METRICS = ("ttfb", "first_body", "headers_to_body", "total")


async def measure(url, body, concurrency, samples):
    import aiohttp

    limit = asyncio.Semaphore(concurrency)

    async def request():
        async with limit:
            start = perf_counter()
            try:
                async with session.request(
                    "POST" if body is not None else "GET", url,
                    json=body, allow_redirects=False,
                ) as response:
                    headers = perf_counter()
                    first = await response.content.read(1)
                    first_body = perf_counter()
                    rest = await response.read()
                    return {"status": response.status,
                            "size": len(first) + len(rest),
                            "ttfb": headers - start,
                            "first_body": first_body - start,
                            "headers_to_body": first_body - headers,
                            "total": perf_counter() - start}
            except (aiohttp.ClientError, asyncio.TimeoutError) as error:
                return {"error": str(error)}

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=concurrency),
        timeout=aiohttp.ClientTimeout(total=5), auto_decompress=False,
        headers={"Accept-Encoding": "identity"},
    ) as session:
        rows = await asyncio.gather(*(request() for _ in range(samples)))
    return rows, type(asyncio.get_running_loop()).__module__


def client_probe(url, body, concurrency, cpus, size, path, samples=1000):
    previous = os.sched_getaffinity(0)
    try:
        os.sched_setaffinity(0, {int(cpu) for cpu in cpus.split(",")})
        rows, loop = asyncio.run(measure(url, body, concurrency, samples))
    finally:
        os.sched_setaffinity(0, previous)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    assert loop.startswith("asyncio"), "client must use the stdlib loop"
    assert all(r.get("status") == 200 and r.get("size") == size
               for r in rows), path
    timings = {}
    for name in METRICS:
        values = quantiles([r[name] for r in rows], n=100, method="inclusive")
        timings[name] = {f"p{p}": values[p - 1] for p in (50, 95, 99)}
    return {"requests": samples, "concurrency": concurrency, "loop": loop,
            "timings": timings, "raw": path.name}
