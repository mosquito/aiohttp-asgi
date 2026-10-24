# Quickstart

This page shows a server which answers from both frameworks, and then the
command line server.

## Install the package

```bash
pip install aiohttp-asgi
```

FastAPI and Starlette are not dependencies of this package. Install the
framework of the ASGI application separately:

```bash
pip install fastapi
```

## Serve an ASGI application beside aiohttp handlers

Create `example.py`:

```python
from aiohttp import web
from fastapi import FastAPI

from aiohttp_asgi import ASGIResource

asgi_app = FastAPI()


@asgi_app.get("/users/{user_id}")
async def get_user(user_id: int):
    return {"user_id": user_id}


async def aiohttp_handler(request: web.Request) -> web.Response:
    return web.Response(text="This handler is an aiohttp handler")


aiohttp_app = web.Application()

# The ASGI application answers under the /api prefix.
asgi_resource = ASGIResource(asgi_app, root_path="/api")
aiohttp_app.router.register_resource(asgi_resource)

# The aiohttp routes stay outside of that prefix.
aiohttp_app.router.add_get("/ping", aiohttp_handler)

# The ASGI application gets the startup and shutdown events.
asgi_resource.lifespan_mount(aiohttp_app)


if __name__ == "__main__":
    web.run_app(aiohttp_app)
```

Start it:

```bash
python example.py
```

Both frameworks now answer on the same port:

```bash
curl http://127.0.0.1:8080/api/users/42
# {"user_id":42}

curl http://127.0.0.1:8080/ping
# This handler is an aiohttp handler
```

:::{important}
The resource takes every request which starts with `root_path`, therefore the
`aiohttp` routes must stay outside of that prefix. The default `root_path` is
`/`, which takes every request; in that case add the `aiohttp` routes before
the resource. The [hybrid application](hybrid.md) page uses this order.
:::

## Serve an ASGI application without aiohttp code

The package installs the `aiohttp-asgi` command. It takes the application in
the `module_name:attribute` format:

```python
# test_app.py
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route


async def homepage(request):
    return JSONResponse({"hello": "world"})


application = Starlette(debug=True, routes=[Route("/", endpoint=homepage)])
```

```bash
aiohttp-asgi --address 127.0.0.1 --port 8080 test_app:application
```

The same server starts through the module:

```bash
python -m aiohttp_asgi --address 127.0.0.1 --port 8080 test_app:application
```

The [command line server](cli.md) page describes the worker processes and the
event loop options.

## Next steps

- [Use the resource in an aiohttp application](aiohttp-application.md) for
  WebSockets, lifespan and prefixes.
- [How it works](how-it-works.md) explains the request and response path.
- [Limitations](limitations.md) lists what the adapter does not do.
