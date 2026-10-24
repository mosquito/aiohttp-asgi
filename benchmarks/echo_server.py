"""Native aiohttp echo backend; no ASGI or JSON serialization on the hot path."""

import asyncio
from functools import partial
import os
import sys

from aiohttp import web

from aiohttp_asgi.__main__ import bind_socket, run_server

requests = 0


async def echo(request):
    global requests
    requests += 1
    return web.Response(body=await request.read(), content_type="application/json")


async def worker(request):
    return web.json_response({
        "pid": os.getpid(), "requests": requests,
        "loop": type(asyncio.get_running_loop()).__module__,
    })


def create_app():
    app = web.Application()
    app.router.add_post("/echo", echo)
    app.router.add_get("/__worker", worker)
    return app


def serve(sock):
    import uvloop

    uvloop.run(run_server(create_app(), sock))


if __name__ == "__main__":
    import forklib

    with bind_socket(address="127.0.0.1", port=18081) as sock:
        forklib.fork(int(sys.argv[1]), partial(serve, sock))
