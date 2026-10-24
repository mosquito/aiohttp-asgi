import asyncio
import importlib
import importlib.util
import logging
import os
import signal
import socket
from argparse import ArgumentParser, ArgumentTypeError
from functools import partial
from typing import Any

import aiohttp.web

from aiohttp_asgi import ASGIResource
from aiohttp_asgi.resource import ASGIApplicationType


# The workers option needs fork, which Windows has not, and forklib, which
# the package requires on Linux only.
WORKERS_SUPPORTED = (
    hasattr(os, "fork") and importlib.util.find_spec("forklib") is not None
)
# The CLI offers the event loops which this installation has. find_spec does
# not import the module, so the parent process does not load an optional loop
# before the fork.
EVENT_LOOPS = [
    name for name in ("rloop", "uvloop")
    if importlib.util.find_spec(name) is not None
] + ["stdlib"]

DEFAULT_EVENT_LOOP = EVENT_LOOPS[0]


parser = ArgumentParser(prog="aiohttp-asgi")
group = parser.add_argument_group("HTTP options")
group.add_argument("-a", "--address", help="Listen address", default="::1")
group.add_argument(
    "-p", "--port", help="Listen port", type=int, default=8080,
)
group.add_argument("--reuse-addr", action="store_true")
group.add_argument("--reuse-port", action="store_true")


parser.add_argument(
    "--log-level", default="info", choices=[
        "debug", "info", "warning", "error", "critical",
    ],
)
parser.add_argument(
    "--event-loop", choices=EVENT_LOOPS, default=DEFAULT_EVENT_LOOP,
    help="Event loop implementation (default: %(default)s)",
)

if WORKERS_SUPPORTED:
    parser.add_argument(
        "-w", "--workers", type=int, default=1,
        help=(
            "Number of worker processes. The parent binds the socket and "
            "forks the workers, so all workers accept connections from one "
            "shared socket. Zero starts one worker for each CPU."
        ),
    )
elif hasattr(os, "fork"):
    # Tell the user how to get the option, because an unknown argument gives
    # an unclear message.
    parser.epilog = (
        "Install forklib (pip install forklib) to start more than one"
        " worker process."
    )


def parse_app_spec(spec: str) -> str:
    """
    Check the "module_name:asgi_application" format.

    This function does not import the module, because the import must happen
    in the worker process, after the fork.
    """
    module_name, _, asgi_app = spec.partition(":")

    if not module_name or not asgi_app:
        raise ArgumentTypeError(
            "Should like \"module_name:asgi_application\" not %r" % (spec,),
        )

    return spec


parser.add_argument(
    "application", help="ASGI application module",
    type=parse_app_spec,
)


log = logging.getLogger()


def new_event_loop(
    implementation: str = DEFAULT_EVENT_LOOP,
) -> asyncio.AbstractEventLoop:
    """
    Create the event loop for the server.

    Call this in the worker process so optional loops are imported and
    created after the fork.
    """
    log.debug("Using the %s event loop", implementation)

    if implementation == "stdlib":
        return asyncio.new_event_loop()

    return importlib.import_module(implementation).new_event_loop()


def load_app(spec: str) -> ASGIApplicationType:
    """
    Import the ASGI application from the "module_name:asgi_application" spec.

    Call this in the worker process. An application can start threads or
    event loops on import, and the fork does not copy them correctly.
    """
    module_name, _, asgi_app = spec.partition(":")

    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ImportError(
            "Can not import module %r" % (module_name,),
        ) from exc

    return getattr(module, asgi_app)


def bind_socket(
    *args: Any, address: str, port: int,
    reuse_addr: bool = True, reuse_port: bool = False,
) -> socket.socket:
    if not args:
        if ":" in address:
            args = (socket.AF_INET6, socket.SOCK_STREAM)
        else:
            args = (socket.AF_INET, socket.SOCK_STREAM)

    sock = socket.socket(*args)
    sock.setblocking(False)

    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, int(reuse_addr))
    if hasattr(socket, "SO_REUSEPORT"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, int(reuse_port))
    else:
        log.warning("SO_REUSEPORT is not implemented by underlying library.")

    sock.bind((address, port))
    sock_addr = sock.getsockname()[:2]

    if sock.family == socket.AF_INET6:
        log.info("Listening http://[%s]:%s", *sock_addr)
    else:
        log.info("Listening http://%s:%s", *sock_addr)

    return sock


def stop_on_signal(stop: asyncio.Event) -> None:
    """
    Set the stop event on SIGINT and SIGTERM.

    The server stops from a signal callback, because an exception from a
    signal handler does not leave every event loop implementation, and in a
    worker it can also die inside the request handler task.
    """
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            # Windows event loops have no signal handlers.
            signal.signal(
                sig, lambda *_: loop.call_soon_threadsafe(stop.set),
            )


async def run_server(
    app: aiohttp.web.Application, sock: socket.socket,
) -> None:
    """Serve the application on the bound socket until a signal arrives."""
    stop = asyncio.Event()
    stop_on_signal(stop)
    runner = aiohttp.web.AppRunner(app)

    try:
        await runner.setup()
        site = aiohttp.web.SockSite(runner, sock)
        await site.start()
        await stop.wait()
    finally:
        log.debug("Stopping the server")
        await runner.cleanup()


def serve(
    spec: str, sock: socket.socket, event_loop: str = DEFAULT_EVENT_LOOP,
) -> None:
    """
    Import the application and run the server on the bound socket.

    This function runs in the worker process, therefore it creates the event
    loop after the fork.
    """
    app = aiohttp.web.Application()
    resource = ASGIResource(load_app(spec))
    app.router.register_resource(resource)
    resource.lifespan_mount(app)

    loop = new_event_loop(event_loop)
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(run_server(app, sock))
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


def main() -> None:
    arguments = parser.parse_args()
    logging.basicConfig(level=getattr(logging, arguments.log_level.upper()))

    workers = getattr(arguments, "workers", 1)

    with bind_socket(
            address=arguments.address,
            port=arguments.port,
            reuse_addr=arguments.reuse_addr,
            reuse_port=arguments.reuse_port,
    ) as sock:
        if workers == 1:
            serve(arguments.application, sock, arguments.event_loop)
            return

        # Import forklib when the user asks for more than one worker,
        # because the package requires it on Linux only.
        import forklib

        forklib.fork(workers, partial(
            serve, arguments.application, sock, arguments.event_loop,
        ))


if __name__ == "__main__":
    main()
