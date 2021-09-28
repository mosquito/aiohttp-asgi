import aiohttp
import pytest
from aiohttp import web, test_utils
from aiohttp_asgi import ASGIResource


@pytest.fixture
def asgi_resource():
    async def asgi_app(scope, receive, send):
        while True:
            payload = await receive()

            if payload.get("type") != "http.request":
                continue

            data = 'a' * 65600 * 1024

            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": []
            })

            await send({
                "type": "http.response.body",
                "body": data.encode()
            })

    return ASGIResource(asgi_app, root_path="/")


@pytest.fixture
def aiohttp_app():
    return web.Application()


@pytest.fixture
async def client(loop, asgi_resource, aiohttp_app):
    aiohttp_app.router.register_resource(asgi_resource)

    asgi_resource.lifespan_mount(
        aiohttp_app,
        startup=False,
        shutdown=False,
    )

    test_server = test_utils.TestServer(aiohttp_app)
    test_client = test_utils.TestClient(test_server)

    await test_client.start_server()

    try:
        yield test_client
    finally:
        await test_server.close()
        await test_client.close()


async def test_basic(loop, client: test_utils.TestClient):
    async with client.get("/") as response:
        response.raise_for_status()
        body = await response.read()
        assert body
