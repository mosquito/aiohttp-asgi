import httpx

from benchmarks.fastapi_app import CASES, app


async def test_fastapi_workloads_and_validation():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test",
    ) as client:
        for name, case in CASES.items():
            if name.startswith("proxy-"):
                continue
            if case["body"] is None:
                response = await client.get(case["path"])
            else:
                response = await client.post(case["path"], json=case["body"])
            assert response.status_code == 200
            assert response.json() == case["expected"]
        assert (await client.get("/items/not-an-int")).status_code == 422
        assert (await client.get("/items/42?quantity=0")).status_code == 422
        response = await client.post("/orders", json={
            "customer_id": 7, "items": [{"item_id": 42, "quantity": 0}],
        })
        assert response.status_code == 422


async def test_proxy_clients_echo_and_close_sessions(aiohttp_server, monkeypatch):
    from benchmarks import fastapi_app
    from benchmarks.echo_server import create_app

    backend = await aiohttp_server(create_app())
    monkeypatch.setattr(fastapi_app, "UPSTREAM", str(backend.make_url("")))
    async with fastapi_app.lifespan(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            for name, case in CASES.items():
                if not name.startswith("proxy-"):
                    continue
                response = await client.post(case["path"], json=case["body"])
                assert response.status_code == 200
                assert response.json() == case["expected"]
                assert response.headers["content-type"] == "application/json"
            assert (await client.post("/proxy/unknown", json={})).status_code == 422
    assert app.state.aiohttp_client.closed
    assert app.state.httpx_client.is_closed


def test_daphne_proxy_is_rejected_before_starting_servers(monkeypatch, capsys):
    import sys
    import pytest
    from benchmarks.run import main

    monkeypatch.setattr(sys, "argv", [
        "benchmarks.run", "--servers", "daphne", "--workloads", "proxy-httpx-1k",
        "--output", "/unused", "--revision", "test",
    ])
    with pytest.raises(SystemExit, match="2"):
        main()
    assert "Daphne has no ASGI lifespan" in capsys.readouterr().err
