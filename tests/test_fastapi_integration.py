import aiohttp
import pytest
from async_generator import yield_, async_generator
from aiohttp import web, test_utils
from fastapi import FastAPI
from starlette.requests import Request as ASGIRequest
from starlette.websockets import WebSocket as ASGIWebSocket, WebSocketDisconnect

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
            "root_path": request.scope.get("root_path")
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
@async_generator
async def client(asgi_resource, aiohttp_app):
    aiohttp_app.router.register_resource(asgi_resource)

    asgi_resource.lifespan_mount(
        aiohttp_app,
        startup=True,
        shutdown=True,
    )

    test_server = test_utils.TestServer(aiohttp_app)
    test_client = test_utils.TestClient(test_server)

    await test_client.start_server()

    try:
        await yield_(test_client)
    finally:
        await test_server.close()
        await test_client.close()


async def test_route_asgi(client: test_utils.TestClient):
    async with client.get("/asgi") as response:
        response.raise_for_status()
        body = await response.json()

    assert body == {'message': 'Hello World', 'root_path': ''}

    async with client.get("/not-found") as response:
        with pytest.raises(aiohttp.ClientError) as err:
            response.raise_for_status()

        assert err.value.status == 404


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

