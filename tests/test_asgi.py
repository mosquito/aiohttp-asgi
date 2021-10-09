from io import BytesIO

import pytest
import string
from aiohttp import test_utils, web

from aiohttp_asgi import ASGIResource


ASGI_LONG_BODY_PARTS = 10
ASGI_LONG_BODY = string.ascii_lowercase.encode() * 1024


@pytest.fixture
def asgi_resource():
    async def asgi_app(scope, receive, send):
        while True:
            payload = await receive()

            if payload.get("type") != "http.request":
                continue

            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [],
            })

            for i in range(ASGI_LONG_BODY_PARTS - 1):
                await send({
                    "type": "http.response.body",
                    "body": ASGI_LONG_BODY,
                    "more_body": True,
                })

            await send({
                "type": "http.response.body",
                "body": ASGI_LONG_BODY,
                "more_body": False,
            })

            return

    return ASGIResource(asgi_app, root_path="/")


@pytest.fixture
def aiohttp_app():
    return web.Application()


@pytest.fixture
async def client(loop, asgi_resource, aiohttp_app):
    aiohttp_app.router.register_resource(asgi_resource)

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

        with BytesIO() as fp:
            async for chunk in response.content.iter_any():
                fp.write(chunk)
            body = fp.getvalue()

        assert body

        body_len = len(body)
        expected_len = len(ASGI_LONG_BODY) * ASGI_LONG_BODY_PARTS
        assert body_len == expected_len
