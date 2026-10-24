import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from statistics import median
import sys
from threading import Thread
import time

import pytest

from benchmarks.latency import client_probe


@pytest.mark.skipif(sys.platform != "linux", reason="taskset requires Linux")
def test_ttfb_precedes_delayed_body(tmp_path):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.flush()
            time.sleep(0.05)
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            path = tmp_path / "client.jsonl"
            affinity = os.sched_getaffinity(0)
            result = client_probe(
                f"http://127.0.0.1:{server.server_port}/", None, 4,
                str(min(os.sched_getaffinity(0))), 2, path, samples=20,
            )
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            assert result["requests"] == 20
            assert median(r["headers_to_body"] for r in rows) >= 0.04
            assert result["timings"]["ttfb"]["p99"] < (
                result["timings"]["total"]["p99"]
            )
            assert os.sched_getaffinity(0) == affinity
            rejected = tmp_path / "wrong-size.jsonl"
            with pytest.raises(AssertionError):
                client_probe(
                    f"http://127.0.0.1:{server.server_port}/", None, 4,
                    str(min(affinity)), 3, rejected, samples=2,
                )
            assert rejected.exists()
            assert os.sched_getaffinity(0) == affinity
        finally:
            server.shutdown()
            thread.join()
