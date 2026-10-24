import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from urllib.error import URLError

import pytest

from aiohttp_asgi.__main__ import (
    EVENT_LOOPS, WORKERS_SUPPORTED, new_event_loop,
)
from tests.test_cli import get_free_port, request_worker


@pytest.mark.parametrize("installed", [
    [], ["uvloop"], ["rloop"], ["uvloop", "rloop"],
])
def test_choices_only_include_installed_loops(installed):
    code = """
import importlib.util
import json
import sys
original = importlib.util.find_spec
installed = json.loads(sys.argv[1])
def find_spec(name, *args, **kwargs):
    if name in ('uvloop', 'rloop'):
        return object() if name in installed else None
    return original(name, *args, **kwargs)
importlib.util.find_spec = find_spec
from aiohttp_asgi.__main__ import EVENT_LOOPS, parser
args = parser.parse_args(['module:application'])
print(json.dumps([EVENT_LOOPS, args.event_loop]))
"""
    choices, default = json.loads(subprocess.check_output(
        [sys.executable, "-c", code, json.dumps(installed)], text=True,
    ))
    assert set(choices) == {"stdlib", *installed}
    expected = next(
        (name for name in ("rloop", "uvloop") if name in installed), "stdlib",
    )
    assert choices[0] == default == expected


@pytest.mark.parametrize("implementation", EVENT_LOOPS)
def test_event_loop_runs(implementation):
    loop = new_event_loop(implementation)
    try:
        expected = "asyncio" if implementation == "stdlib" else implementation
        assert type(loop).__module__.startswith(expected)
        assert loop.run_until_complete(asyncio.sleep(0, result=42)) == 42
    finally:
        loop.close()


@pytest.mark.skipif(not WORKERS_SUPPORTED, reason="forklib is not installed")
@pytest.mark.parametrize("implementation", EVENT_LOOPS)
@pytest.mark.parametrize("workers", [1, 4])
def test_cli_worker_event_loops(implementation, workers):
    port = get_free_port()
    command = [
        sys.executable, "-m", "aiohttp_asgi", "--address", "127.0.0.1",
        "--port", str(port), "--workers", str(workers),
        "--event-loop", implementation, "--log-level", "warning",
        "tests.cli_app:application",
    ]
    process = subprocess.Popen(command, start_new_session=True)
    pids: set[int] = set()
    modules: set[str] = set()
    try:
        deadline = time.monotonic() + 15
        while len(pids) < workers and time.monotonic() < deadline:
            assert process.poll() is None
            try:
                pid, module = request_worker(f"http://127.0.0.1:{port}/")
            except (URLError, OSError):
                time.sleep(0.05)
                continue
            pids.add(pid)
            modules.add(module)
        assert len(pids) == workers
        expected = "asyncio" if implementation == "stdlib" else implementation
        assert all(module.startswith(expected) for module in modules)
    finally:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
