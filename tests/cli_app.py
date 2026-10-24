import asyncio
import os
import signal

started = False


async def stop_during_startup(scope, receive, send):
    assert scope["type"] == "lifespan"
    assert (await receive())["type"] == "lifespan.startup"
    os.kill(os.getpid(), signal.SIGTERM)
    await send({"type": "lifespan.startup.complete"})
    assert (await receive())["type"] == "lifespan.shutdown"
    await send({"type": "lifespan.shutdown.complete"})


async def application(scope, receive, send):
    """Answer with the worker PID and the event loop implementation."""
    global started
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                started = True
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                started = False
                await send({"type": "lifespan.shutdown.complete"})
                return

    assert started, "CLI must run lifespan startup before serving requests"
    await http_only_application(scope, receive, send)


async def http_only_application(scope, receive, send):
    assert scope["type"] == "http"
    while True:
        payload = await receive()

        if payload.get("type") != "http.request":
            continue

        loop_module = type(asyncio.get_running_loop()).__module__

        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain")],
        })

        await send({
            "type": "http.response.body",
            "body": ("%d %s" % (os.getpid(), loop_module)).encode(),
        })

        return
