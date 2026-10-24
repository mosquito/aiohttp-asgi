import asyncio
import os
import signal
import socket
import subprocess
import sys
import time
from argparse import ArgumentTypeError
from pathlib import Path
from typing import Set, Tuple
from urllib.error import URLError
from urllib.request import urlopen

import pytest

from aiohttp_asgi.__main__ import (
    DEFAULT_EVENT_LOOP, EVENT_LOOPS, WORKERS_SUPPORTED, load_app,
    new_event_loop, parse_app_spec, parser,
)


PROJECT_ROOT = Path(__file__).parent.parent
START_TIMEOUT = 30
STOP_TIMEOUT = 10
WORKERS = 2


def test_parse_app_spec():
    assert parse_app_spec("module:application") == "module:application"

    for spec in ("module", "module:", ":application", ""):
        with pytest.raises(ArgumentTypeError):
            parse_app_spec(spec)


def test_parse_args_does_not_import_application():
    # The worker process imports the application after the fork, so the
    # argument parser must accept a module which is not importable.
    arguments = parser.parse_args(["no_such_module:application"])
    assert arguments.application == "no_such_module:application"

    with pytest.raises(ImportError):
        load_app("no_such_module:application")


def test_load_app():
    assert load_app("tests.cli_app:application") is not None


def test_event_loop_argument():
    # Prefer the first installed loop in the configured priority order.
    assert "stdlib" in EVENT_LOOPS
    assert DEFAULT_EVENT_LOOP == EVENT_LOOPS[0]

    arguments = parser.parse_args(["module:application"])
    assert arguments.event_loop == DEFAULT_EVENT_LOOP

    arguments = parser.parse_args(
        ["--event-loop", "stdlib", "module:application"],
    )
    assert arguments.event_loop == "stdlib"

    with pytest.raises(SystemExit):
        parser.parse_args(["--event-loop", "noloop", "module:application"])


def test_stdlib_event_loop():
    loop = new_event_loop("stdlib")
    try:
        assert isinstance(loop, asyncio.AbstractEventLoop)
    finally:
        loop.close()


@pytest.mark.skipif(not WORKERS_SUPPORTED, reason="forklib is not installed")
def test_workers_argument():
    assert parser.parse_args(["module:application"]).workers == 1
    assert parser.parse_args(
        ["-w", "3", "module:application"],
    ).workers == 3


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def get_loop_module(implementation: str) -> str:
    """Return the module of the event loop which the CLI creates."""
    loop = new_event_loop(implementation)
    try:
        return type(loop).__module__
    finally:
        loop.close()


def request_worker(url: str) -> Tuple[int, str]:
    """Return the PID and the event loop implementation of the worker."""
    with urlopen(url, timeout=5) as response:
        assert response.status == 200
        pid, loop_module = response.read().decode().split(" ", 1)
        return int(pid), loop_module


def start_server(
    port: int, event_loop_name: str, workers: int,
    application: str = "tests.cli_app:application",
):
    command = [
        sys.executable, "-m", "aiohttp_asgi",
        "--address", "127.0.0.1",
        "--port", str(port),
        "--event-loop", event_loop_name,
        application,
    ]

    if WORKERS_SUPPORTED:
        command[-1:] = ["--workers", str(workers), command[-1]]

    return subprocess.Popen(
        command, cwd=str(PROJECT_ROOT),
        env=dict(os.environ, PYTHONPATH=str(PROJECT_ROOT)),
        start_new_session=True,
    )


def wait_for_answer(url: str, process) -> None:
    deadline = time.monotonic() + START_TIMEOUT

    while time.monotonic() < deadline:
        assert process.poll() is None, "The server exited too early"

        try:
            request_worker(url)
            return
        except (URLError, OSError):
            time.sleep(0.1)

    raise AssertionError("The server gave no answer")


@pytest.mark.parametrize("workers", [1, WORKERS])
@pytest.mark.parametrize("event_loop_name", EVENT_LOOPS)
@pytest.mark.parametrize("application", [
    "tests.cli_app:application", "tests.cli_app:http_only_application",
])
def test_sigterm_stops_server(event_loop_name, workers, application):
    if workers != 1 and not WORKERS_SUPPORTED:
        pytest.skip("forklib is not installed")

    port = get_free_port()
    process = start_server(port, event_loop_name, workers, application)

    try:
        wait_for_answer("http://127.0.0.1:%d/" % port, process)
        process.terminate()
        assert process.wait(timeout=STOP_TIMEOUT) == 0
    finally:
        if process.poll() is None:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            process.wait(timeout=STOP_TIMEOUT)


@pytest.mark.parametrize("event_loop_name", EVENT_LOOPS)
def test_sigterm_during_startup(event_loop_name):
    process = start_server(
        get_free_port(), event_loop_name, 1,
        "tests.cli_app:stop_during_startup",
    )
    try:
        assert process.wait(timeout=STOP_TIMEOUT) == 0
    finally:
        if process.poll() is None:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            process.wait(timeout=STOP_TIMEOUT)


@pytest.mark.skipif(not WORKERS_SUPPORTED, reason="forklib is not installed")
@pytest.mark.parametrize("event_loop_name", EVENT_LOOPS)
def test_cli_workers(event_loop_name):
    port = get_free_port()
    url = "http://127.0.0.1:%d/" % port

    env = dict(os.environ, PYTHONPATH=str(PROJECT_ROOT))
    process = subprocess.Popen(
        [
            sys.executable, "-m", "aiohttp_asgi",
            "--address", "127.0.0.1",
            "--port", str(port),
            "--workers", str(WORKERS),
            "--event-loop", event_loop_name,
            "tests.cli_app:application",
        ],
        cwd=str(PROJECT_ROOT), env=env, start_new_session=True,
    )

    pids: Set[int] = set()
    loop_modules: Set[str] = set()
    deadline = time.monotonic() + START_TIMEOUT

    try:
        while time.monotonic() < deadline:
            assert process.poll() is None, "The server exited too early"

            try:
                pid, loop_module = request_worker(url)
            except (URLError, OSError):
                time.sleep(0.1)
                continue

            pids.add(pid)
            loop_modules.add(loop_module)

            if len(pids) == WORKERS:
                break

        # The parent process binds the socket and supervises the workers,
        # therefore the answers come from the forked children.
        assert pids, "The server gave no answer"
        assert process.pid not in pids
        assert len(pids) == WORKERS
        assert loop_modules == {get_loop_module(event_loop_name)}
    finally:
        process.terminate()

        try:
            process.wait(timeout=STOP_TIMEOUT)
        except subprocess.TimeoutExpired:
            # Some event loops do not stop the server on SIGTERM. Kill the
            # process group, because the workers are separate processes.
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            process.wait(timeout=STOP_TIMEOUT)
