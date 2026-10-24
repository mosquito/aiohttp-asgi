# Limitations

The adapter is a thin bridge, therefore some `aiohttp` and ASGI mechanisms
need attention.

## The resource takes no prefix from aiohttp

`ASGIResource.add_prefix()` raises `NotImplementedError`, therefore
`Application.add_subapp()` does not accept an application which holds the
resource:

```python
subapp = web.Application()
subapp.router.register_resource(ASGIResource(asgi_app))

# NotImplementedError
aiohttp_app.add_subapp("/sub", subapp)
```

Use the `root_path` argument of the resource instead of a subapp prefix:

```python
aiohttp_app.router.register_resource(
    ASGIResource(asgi_app, root_path="/sub"),
)
```

`Application.add_domain()` works, because it gives no prefix to the
resources.

## A catch-all resource changes the registration order

With the default `root_path="/"` the resource accepts every path. `aiohttp`
reuses the last added resource when its `raw_match()` accepts the path,
therefore a `router.add_get()` call after such a resource raises
`AttributeError: 'ASGIResource' object has no attribute 'add_route'`. Add the
`aiohttp` routes before the resource, or give the resource a prefix. See
[Hybrid application](hybrid.md).

## The command line server sends no lifespan events

The `aiohttp-asgi` command serves the requests, but it does not send
`lifespan.startup` and `lifespan.shutdown`. An application which needs those
events runs through an `aiohttp` application with
{meth}`~aiohttp_asgi.ASGIResource.lifespan_mount`.

## The resource gives no routes to aiohttp

The resource reports no routes, so `len(resource)` is zero and the iteration
over it gives nothing. `get_info()` raises `NotImplementedError`, and
`url_for()` returns the `root_path`. The `aiohttp` tools which list the
routes, for example a route table in a debug page, therefore show no ASGI
route.

## Worker processes need fork

The `-w/--workers` option of the command needs `fork` and forklib, so it
exists on POSIX systems only. Windows runs one process.

## The ASGI extensions are not implemented

The adapter speaks the HTTP and the WebSocket part of the ASGI specification.
The scope holds no `extensions` key, therefore an application which needs an
extension, for example `http.response.push` or a path send extension, gets no
answer for it.

## The deprecated set_current_app()

`ASGIMatchInfo.set_current_app()` is deprecated. Use `add_app()`, which the
`aiohttp` application does itself.

## Versions

- Python 3.9 or later.
- `aiohttp` 3.x. The adapter uses the match info and the resource interfaces
  of that series.
