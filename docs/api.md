# API reference

## aiohttp_asgi

```{eval-rst}
.. autoclass:: aiohttp_asgi.ASGIResource
   :members:
   :special-members: __init__
```

## aiohttp_asgi.resource

```{eval-rst}
.. autoclass:: aiohttp_asgi.resource.ASGIMatchInfo
   :members:

.. autoclass:: aiohttp_asgi.resource.ASGIContext
   :members:
```

### Type aliases

`aiohttp_asgi.resource` gives the type aliases of the ASGI protocol:

```{list-table}
:header-rows: 1
:widths: 30 70

* - Alias
  - Meaning
* - `ASGIScopeType`
  - The scope: a mutable mapping with string keys
* - `ASGIReceiveType`
  - The `receive` callable, which gives the next message
* - `ASGISendType`
  - The `send` callable, which takes a message
* - `ASGIApplicationType`
  - The application: a callable which takes the scope, `receive` and `send`
```

## aiohttp_asgi.__main__

The command line server. The functions are useful for a custom entry point
which needs the same behaviour.

```{eval-rst}
.. autofunction:: aiohttp_asgi.__main__.parse_app_spec

.. autofunction:: aiohttp_asgi.__main__.load_app

.. autofunction:: aiohttp_asgi.__main__.new_event_loop

.. autofunction:: aiohttp_asgi.__main__.bind_socket

.. autofunction:: aiohttp_asgi.__main__.stop_on_signal

.. autofunction:: aiohttp_asgi.__main__.run_server

.. autofunction:: aiohttp_asgi.__main__.serve

.. autofunction:: aiohttp_asgi.__main__.main
```
