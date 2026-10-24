aiohttp-asgi
============

[![PyPI - License](https://img.shields.io/pypi/l/aiohttp-asgi)](https://pypi.org/project/aiohttp-asgi) [![Wheel](https://img.shields.io/pypi/wheel/aiohttp-asgi)](https://pypi.org/project/aiohttp-asgi) [![PyPI](https://img.shields.io/pypi/v/aiohttp-asgi)](https://pypi.org/project/aiohttp-asgi) [![PyPI](https://img.shields.io/pypi/pyversions/aiohttp-asgi)](https://pypi.org/project/aiohttp-asgi) [![Coverage Status](https://coveralls.io/repos/github/mosquito/aiohttp-asgi/badge.svg?branch=master)](https://coveralls.io/github/mosquito/aiohttp-asgi?branch=master) ![tests](https://github.com/mosquito/aiohttp-asgi/workflows/tests/badge.svg?branch=master)

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

The faster event loops are optional extras:

```bash
pip install "aiohttp-asgi[uvloop]"
pip install "aiohttp-asgi[rloop]"
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

#### Multiple worker processes

The `-w/--workers` option starts more than one worker process. The parent
process binds the socket, then
[forklib](https://github.com/mosquito/forklib) forks the workers, so all
workers accept connections from one shared socket. The parent process does not
serve requests, it supervises the workers. Zero starts one worker for each CPU.

```bash
aiohttp-asgi --workers 4 test_app:application
```

The package requires forklib on Linux, therefore the option works there
without an additional step. On other POSIX systems install forklib with
`pip install forklib`. The CLI shows the option only when forklib is
installed, so the option is not available on Windows, which has no `fork`.

Each worker imports the ASGI application after the fork, because an
application can start threads or event loops on import, and the fork does not
copy them correctly.

#### Event loop

Choose an event loop with `--event-loop=stdlib`, `--event-loop=uvloop` or
`--event-loop=rloop`. The CLI only offers optional loops that are installed;
`stdlib` is always available. The default preference order is
`rloop`, then [uvloop](https://github.com/MagicStack/uvloop), then stdlib.
Each worker imports and creates its event loop after the fork.

```bash
pip install "aiohttp-asgi[uvloop]"
aiohttp-asgi --workers 4 --event-loop=uvloop test_app:application
```

Development
-----------

The project uses [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-extras
uv run pytest
uv run ruff check
uv run mypy
```
