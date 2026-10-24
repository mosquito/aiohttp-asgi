"""Summarize raw oha results as CSV; latency values are in milliseconds."""

import csv
import json
from pathlib import Path
from statistics import median
import sys

from benchmarks.latency import METRICS


def summarize(directory):
    groups = {}
    metadata = json.loads((directory / "metadata.json").read_text())
    for path in directory.glob("*-c*.json"):
        data = json.loads(path.read_text())
        case = data["benchmark"]
        key = (case["server"], case["workload"], case["concurrency"])
        assert not data["errorDistribution"], path
        assert set(data["statusCodeDistribution"]) == {"200"}, path
        groups.setdefault(key, []).append(data)
    expected = (
        len(metadata["servers"])
        * len(metadata["workloads"])
        * len(metadata["concurrency"])
    )
    assert len(groups) == expected, "incomplete matrix"
    writer = csv.writer(sys.stdout)
    writer.writerow([
        "server", "workload", "concurrency", "runs", "rps_median",
        "rps_min", "rps_max", "p50_ms_median", "p99_ms_median", "errors",
        "body_first_byte_p50_ms_median", "body_first_byte_p99_ms_median",
        "p95_ms_median", "body_first_byte_p95_ms_median",
        *[f"client_{name}_p{p}_ms_median"
          for name in METRICS for p in (50, 95, 99)],
    ])
    for key, runs in sorted(groups.items()):
        assert len(runs) == metadata["repeats"], key
        assert len({r["benchmark"]["repeat"] for r in runs}) == len(runs)
        rps = [r["summary"]["requestsPerSec"] for r in runs]
        has_client = ["client" in r for r in runs]
        assert all(has_client) or not any(has_client), "incomplete client data"
        client = [
            round(median(r["client"]["timings"][name][f"p{p}"] * 1000
                         for r in runs), 3)
            for name in METRICS for p in (50, 95, 99)
        ] if all(has_client) else [""] * (len(METRICS) * 3)
        writer.writerow([
            *key, len(runs), round(median(rps), 2), round(min(rps), 2),
            round(max(rps), 2),
            *[round(median(r["latencyPercentiles"][p] * 1000 for r in runs), 3)
              for p in ("p50", "p99")],
            0,
            *[round(median(r["firstBytePercentiles"][p] * 1000
                           for r in runs), 3)
              for p in ("p50", "p99")],
            *[round(median(r[field]["p95"] * 1000 for r in runs), 3)
              for field in ("latencyPercentiles", "firstBytePercentiles")],
            *client,
        ])


if __name__ == "__main__":
    summarize(Path(sys.argv[1]))
