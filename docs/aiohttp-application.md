# The resource in an aiohttp application

{class}`~aiohttp_asgi.ASGIResource` is an `aiohttp` resource. The router keeps
it with the other resources, therefore the ASGI application gets requests from
the same server, the same event loop and the same process.

## Register the resource

```python
from aiohttp import web

from aiohttp_asgi import ASGIResource

asgi_resource = ASGIResource(asgi_app, root_path="/api")
aiohttp_app.router.register_resource(asgi_resource)
```

The resource takes a request when the request path starts with `root_path`.
The ASGI application gets `root_path` in the scope, so FastAPI and Starlette
match their routes without the prefix: with `root_path="/api"` the request
`GET /api/users/42` reaches the route `/users/42`.

A path which starts with the prefix but has no ASGI route gives the answer of
the ASGI application, usually 404. The `aiohttp` router does not continue the
search.

## Keep the registration order

The default `root_path` is `/`, therefore the resource takes every request.
Add the `aiohttp` routes **before** such a resource:

```python
aiohttp_app = web.Application()

# First the aiohttp routes.
aiohttp_app.router.add_get("/ping", ping_handler)

# Then the catch-all ASGI resource.
aiohttp_app.router.register_resource(ASGIResource(asgi_app))
```

:::{warning}
`aiohttp` reuses the last added resource when its `raw_match()` accepts the
path. A `router.add_get()` call after a resource with `root_path="/"` reaches
the ASGI resource and raises
`AttributeError: 'ASGIResource' object has no attribute 'add_route'`.
A prefix like `root_path="/api"` has not this problem, because `raw_match()`
rejects the other paths.
:::

## Send the lifespan events

{meth}`~aiohttp_asgi.ASGIResource.lifespan_mount` appends a cleanup context to
the `aiohttp` application. The context sends `lifespan.startup` when the
`aiohttp` application starts, and `lifespan.shutdown` when it stops:

```python
asgi_resource.lifespan_mount(aiohttp_app)
```

Without this call the ASGI application gets no lifespan events, so the startup
and shutdown handlers of FastAPI or Starlette do not run. The adapter logs the
result of each event, and waits at most
{attr}`~aiohttp_asgi.ASGIResource.SHUTDOWN_TIMEOUT` seconds for the lifespan
task after the shutdown event.

## WebSockets

The resource makes an `aiohttp` WebSocket response when the request is a
WebSocket handshake, therefore an ASGI WebSocket endpoint works without
additional code:

```python
from starlette.websockets import WebSocket, WebSocketDisconnect


@asgi_app.websocket("/ws")
async def echo(websocket: WebSocket):
    await websocket.accept()

    while True:
        try:
            await websocket.send_json(await websocket.receive_json())
        except WebSocketDisconnect:
            return
```

The adapter reads the `Sec-WebSocket-Protocol` header and gives the
subprotocols to the ASGI application in `scope["subprotocols"]`.

## Middlewares and signals

The resource is part of the `aiohttp` application, therefore the `aiohttp`
middlewares, the `on_response_prepare` signal and the other `aiohttp`
mechanisms also work for the ASGI requests. For example
`normalize_path_middleware` redirects to the path which the ASGI application
needs:

```python
aiohttp_app = web.Application(
    middlewares=[
        web.normalize_path_middleware(remove_slash=True, append_slash=False),
    ],
)
```

## What the ASGI application receives

The adapter builds the scope from the `aiohttp` request:

```{list-table}
:header-rows: 1
:widths: 30 70

* - Scope key
  - Value
* - `type`
  - `http`, or `websocket` for a WebSocket handshake
* - `http_version`
  - `1.1` for a keep-alive connection, else `1.0`
* - `method`
  - The request method
* - `scheme`
  - The request scheme; `ws` or `wss` for a WebSocket
* - `path`
  - The request path
* - `raw_path`
  - The not decoded path, as bytes
* - `root_path`
  - The `root_path` of the resource, without the last slash
* - `query_string`
  - The query string, as bytes
* - `headers`
  - The request headers, as a list of lower case byte pairs
* - `server`
  - The host and the port of the request URL
* - `client`
  - The remote address of the connection, and zero as the port
* - `subprotocols`
  - The WebSocket subprotocols, else `None`
```
