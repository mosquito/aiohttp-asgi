# Hybrid application: move the hot handlers to aiohttp

An ASGI application pays for the ASGI bridge and for the framework which it
runs on. An `aiohttp` handler writes to the response directly, therefore it
does less work for each request. A full rewrite of a large FastAPI
application, however, costs much time and gives much risk.

This package makes the rewrite optional: keep the ASGI application for every
route, and rewrite only the handlers which need the speed. The server stays
one process, and the ASGI application keeps its routes, dependencies and
lifespan.

## The pattern

1. Register the rewritten `aiohttp` handlers first.
2. Register the ASGI application as a catch-all resource after them.

`aiohttp` searches the resources in the registration order, therefore the
rewritten paths go to the `aiohttp` handlers, and every other path goes to the
ASGI application.

```python
from aiohttp import web
from fastapi import FastAPI

from aiohttp_asgi import ASGIResource

asgi_app = FastAPI()


@asgi_app.get("/users/{user_id}")
async def get_user(user_id: int):
    """This route stays on FastAPI."""
    return {"user_id": user_id, "served_by": "fastapi"}


@asgi_app.get("/metrics")
async def metrics():
    """This route gets a faster aiohttp handler below."""
    return {"requests": 0, "served_by": "fastapi"}


async def metrics_handler(request: web.Request) -> web.Response:
    """The rewritten handler. It answers without the ASGI bridge."""
    return web.json_response({"requests": 0, "served_by": "aiohttp"})


aiohttp_app = web.Application()

# 1. The rewritten handlers.
aiohttp_app.router.add_get("/metrics", metrics_handler)

# 2. The ASGI application for everything else.
asgi_resource = ASGIResource(asgi_app)
aiohttp_app.router.register_resource(asgi_resource)
asgi_resource.lifespan_mount(aiohttp_app)


if __name__ == "__main__":
    web.run_app(aiohttp_app)
```

```bash
curl http://127.0.0.1:8080/metrics
# {"requests": 0, "served_by": "aiohttp"}

curl http://127.0.0.1:8080/users/42
# {"user_id":42,"served_by":"fastapi"}
```

The FastAPI route `/metrics` stays in the code. It documents the answer, it
serves the tests of the ASGI application, and it answers again when the
`aiohttp` route goes away.

:::{warning}
Register the `aiohttp` routes before a resource with the default
`root_path="/"`. `aiohttp` reuses the last added resource when its
`raw_match()` accepts the path, therefore a `router.add_get()` call after the
catch-all resource raises
`AttributeError: 'ASGIResource' object has no attribute 'add_route'`.
:::

## Share the state

The two worlds keep their own state, and both run in one process:

- An `aiohttp` handler reads `request.app["key"]`, which the `aiohttp`
  application holds.
- A FastAPI or Starlette handler uses its own dependencies and
  `request.app.state`.

A connection pool, a cache client or another resource therefore needs one
owner. Create it in the `aiohttp` cleanup context, and give the same object to
the ASGI application:

```python
async def database(app: web.Application):
    pool = await create_pool()

    app["pool"] = pool
    asgi_app.state.pool = pool

    yield

    await pool.close()


aiohttp_app.cleanup_ctx.append(database)
```

## Keep the answers equal

A rewritten handler must answer like the ASGI route which it replaces, because
the clients do not see the difference. Useful checks:

- The status code, the headers and the JSON structure.
- The validation errors. FastAPI answers 422 with a body which describes the
  problem; an `aiohttp` handler must answer in the same form when the clients
  read it.
- The authentication. A FastAPI dependency which checks a token must become an
  `aiohttp` middleware or a function which the new handler calls.

Keep a test for each rewritten path, and run it against both answers while the
rewrite continues.

## Measure before the rewrite

Rewrite the handlers which the profile shows, not the handlers which look
slow. A handler which waits for a database gives little to a rewrite, because
the time goes to the database. A handler which serializes much data, or which
answers very often, gives more.
