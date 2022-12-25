aiohttp-asgi
============

[![PyPI - License](https://img.shields.io/pypi/l/aiohttp-asgi)](https://pypi.org/project/aiohttp-asgi) [![Wheel](https://img.shields.io/pypi/wheel/aiohttp-asgi)](https://pypi.org/project/aiohttp-asgi) [![PyPI](https://img.shields.io/pypi/v/aiohttp-asgi)](https://pypi.org/project/aiohttp-asgi) [![PyPI](https://img.shields.io/pypi/pyversions/aiohttp-asgi)](https://pypi.org/project/aiohttp-asgi) [![Coverage Status](https://coveralls.io/repos/github/mosquito/aiohttp-asgi/badge.svg?branch=master)](https://coveralls.io/github/mosquito/aiohttp-asgi?branch=master) ![tox](https://github.com/mosquito/aiohttp-asgi/workflows/tox/badge.svg?branch=master)

This module provides a way to use any ASGI compatible frameworks and aiohttp together.

Example
-------

```python
from aiohttp import web
from fastapi import FastAPI
from starlette.requests import Request as ASGIRequest

from aiohttp_asgi import ASGIResource


asgi_app = FastAPI()


@asgi_app.get("/asgi")
async def root(request: ASGIRequest):
    return {
        "message": "Hello World",
        "root_path": request.scope.get("root_path")
    }


aiohttp_app = web.Application()

# Create ASGIResource which handle
# any request startswith "/asgi"
asgi_resource = ASGIResource(asgi_app, root_path="/asgi")

# Register resource
aiohttp_app.router.register_resource(asgi_resource)

# Mount startup and shutdown events from aiohttp to ASGI app
asgi_resource.lifespan_mount(aiohttp_app)

# Start the application
web.run_app(aiohttp_app)

```

Installation
------------

```bash
pip install aiohttp-asgi
```

ASGI HTTP server
----------------

Command line tool for starting aiohttp web server with ASGI app.

#### Example

Create the `test_app.py`

```python
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route


async def homepage(request):
    return JSONResponse({'hello': 'world'})

routes = [
    Route("/", endpoint=homepage)
]

application = Starlette(debug=True, routes=routes)
```

and run the `test_app.py` with `aiohttp-asgi`

```bash
aiohttp-asgi \
    --address "[::1]" \
    --port 8080 \
    test_app:application
```

alternatively using `python -m`

```bash
python -m aiohttp_asgi \
    --address "[::1]" \
    --port 8080 \
    test_app:application
```
