# aiohttp-asgi

`aiohttp-asgi` runs an ASGI application inside an
[aiohttp](https://docs.aiohttp.org/) web application. The adapter is an
`aiohttp` resource, therefore an ASGI application like FastAPI or Starlette
serves requests next to the `aiohttp` handlers of the same server, in the same
event loop and the same process.

The package also gives a command line server, so an ASGI application runs
without an additional web server.

## When this package helps

```{list-table}
:header-rows: 1
:widths: 40 60

* - Situation
  - What the package gives
* - An `aiohttp` service must also serve a FastAPI or Starlette application
  - One server, one event loop, one process, and no proxy between them
* - An `aiohttp` application moves to ASGI step by step
  - Both frameworks answer on the same port while the migration continues
* - An ASGI application needs an `aiohttp` middleware, signal or subapp
  - The ASGI application becomes a resource of the `aiohttp` router
* - A FastAPI application needs more speed, but a full rewrite costs too much
  - Rewrite the hot handlers as `aiohttp` handlers, and keep the rest on
    FastAPI in one [hybrid application](hybrid.md)
* - A question: does my application run on this adapter, and how fast?
  - The [`aiohttp-asgi` command](cli.md#try-an-application-without-changes)
    serves the application as it is, with no code change
* - A small deployment needs a server for an ASGI application
  - The `aiohttp-asgi` command, with worker processes and a faster event loop
```

## Installation

```bash
pip install aiohttp-asgi
```

## The shortest example

```python
from aiohttp import web
from fastapi import FastAPI

from aiohttp_asgi import ASGIResource

asgi_app = FastAPI()


@asgi_app.get("/hello")
async def hello():
    return {"hello": "world"}


aiohttp_app = web.Application()
asgi_resource = ASGIResource(asgi_app, root_path="/asgi")

aiohttp_app.router.register_resource(asgi_resource)

# Send the ASGI lifespan events with the aiohttp application.
asgi_resource.lifespan_mount(aiohttp_app)

web.run_app(aiohttp_app)
```

`GET /asgi/hello` reaches the FastAPI route. Every other path stays with the
`aiohttp` router.

## Documentation

```{toctree}
:maxdepth: 2

quickstart
aiohttp-application
hybrid
cli
how-it-works
benchmarks
limitations
api
```

## Links

- Source code: <https://github.com/mosquito/aiohttp-asgi>
- Issues: <https://github.com/mosquito/aiohttp-asgi/issues>
- Package: <https://pypi.org/project/aiohttp-asgi/>
