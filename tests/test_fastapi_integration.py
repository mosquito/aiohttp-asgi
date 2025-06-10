import aiohttp
import pytest
from aiohttp import test_utils, web
from fastapi import FastAPI
from starlette.requests import Request as ASGIRequest
from starlette.websockets import WebSocket as ASGIWebSocket
from starlette.websockets import WebSocketDisconnect

from aiohttp_asgi import ASGIResource


@pytest.fixture
def asgi_app():
    return FastAPI()


@pytest.fixture
def routes(asgi_app):
    @asgi_app.get("/asgi")
    async def root(request: ASGIRequest):
        return {
            "message": "Hello World",
            "root_path": request.scope.get("root_path"),
        }

    @asgi_app.websocket("/ws")
    async def websocket_endpoint(websocket: ASGIWebSocket):
        await websocket.accept()

        while True:
            try:
                data = await websocket.receive_json()
                data["echo"] = True
                await websocket.send_json(data)
            except WebSocketDisconnect:
                return


@pytest.fixture
def asgi_resource(routes, asgi_app):
    return ASGIResource(asgi_app, root_path="/")


@pytest.fixture
def aiohttp_app():
    return web.Application()


@pytest.fixture
async def client(asgi_resource, aiohttp_app):
    aiohttp_app.router.register_resource(asgi_resource)

    asgi_resource.lifespan_mount(aiohttp_app)

    test_server = test_utils.TestServer(aiohttp_app)
    test_client = test_utils.TestClient(test_server)

    await test_client.start_server()

    try:
        yield test_client
    finally:
        await test_server.close()
        await test_client.close()


async def test_route_asgi(client: test_utils.TestClient):
    for _ in range(10):
        async with client.get("/asgi") as response:
            response.raise_for_status()
            body = await response.json()

        assert body == {"message": "Hello World", "root_path": ""}

    for _ in range(10):
        async with client.get("/not-found") as response:
            with pytest.raises(aiohttp.ClientError) as err:
                response.raise_for_status()

            assert err.value.status == 404      # type: ignore


async def test_route_ws(client: test_utils.TestClient):
    async with client.ws_connect("/ws") as ws:
        for i in range(10):
            await ws.send_json({"hello": "world", "i": i})
            response = await ws.receive_json()

            assert response == {"hello": "world", "i": i, "echo": True}

        for i in range(10):
            await ws.send_json({"hello": "world", "i": i})

        for i in range(10):
            response = await ws.receive_json()
            assert response == {"hello": "world", "i": i, "echo": True}


@web.middleware
async def dummy_middleware(request, handler):
    return await handler(request)


@pytest.mark.parametrize(
    "middlewares",
    (
        (
            web.normalize_path_middleware(
                remove_slash=True,
                append_slash=False,
            ),
        ),
        (dummy_middleware,),
        (
            web.normalize_path_middleware(
                remove_slash=True,
                append_slash=False,
            ),
            dummy_middleware,
        ),
    ),
)
async def test_normalize_path_middleware(asgi_resource, middlewares):
    aiohttp_app = web.Application(middlewares=middlewares)
    aiohttp_app.router.register_resource(asgi_resource)
    asgi_resource.lifespan_mount(aiohttp_app)

    async with test_utils.TestServer(aiohttp_app) as test_server:
        async with test_utils.TestClient(test_server) as client:
            async with client.get("/asgi") as response:
                response.raise_for_status()
                body = await response.json()

            assert body == {"message": "Hello World", "root_path": ""}

            async with client.get("/not-found") as response:
                with pytest.raises(aiohttp.ClientError) as err:
                    response.raise_for_status()

            assert err.value.status == 404      # type: ignore


def test_get_routes_from_resource(asgi_resource):
    assert len(asgi_resource) == 0

    for _ in asgi_resource:
        # Should be unreachable
        pytest.fail("ASGIResource should not return routes during iteration")
