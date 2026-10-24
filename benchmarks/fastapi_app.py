"""Small REST application: typed queries, nested bodies and response models."""

import asyncio
from contextlib import asynccontextmanager
import os
from typing import Literal

import aiohttp
import httpx
from fastapi import FastAPI, Path, Query, Request, Response
from pydantic import BaseModel, Field

UPSTREAM = os.environ.get("BENCHMARK_UPSTREAM", "http://127.0.0.1:18081")


@asynccontextmanager
async def lifespan(app):
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=100, keepalive_timeout=30),
        timeout=aiohttp.ClientTimeout(total=5), auto_decompress=False,
        headers={"Accept-Encoding": "identity"}, trust_env=False,
    ) as aiohttp_client, httpx.AsyncClient(
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=100,
                            keepalive_expiry=30),
        timeout=5, headers={"Accept-Encoding": "identity"}, trust_env=False,
    ) as httpx_client:
        app.state.aiohttp_client = aiohttp_client
        app.state.httpx_client = httpx_client
        yield


app = FastAPI(lifespan=lifespan)
requests = 0
CATALOG = {
    item_id: {"name": f"Item {item_id}", "price_cents": 1250 + item_id * 10}
    for item_id in range(1, 101)
}


class Quote(BaseModel):
    item_id: int
    name: str
    quantity: int
    currency: Literal["EUR", "USD"]
    total_cents: int
    tags: list[str]


class OrderLine(BaseModel):
    item_id: int = Field(ge=1, le=100)
    quantity: int = Field(ge=1, le=100)


class Order(BaseModel):
    customer_id: int = Field(gt=0)
    items: list[OrderLine]
    coupon: Literal["NONE", "SAVE10"] = "NONE"


class Receipt(BaseModel):
    customer_id: int
    lines: list[Quote]
    discount_cents: int
    total_cents: int


def quote(item_id: int, quantity: int, currency: str) -> dict:
    item = CATALOG[item_id]
    return {
        "item_id": item_id, "name": item["name"], "quantity": quantity,
        "currency": currency, "total_cents": item["price_cents"] * quantity,
        "tags": ["catalog", "in-stock"],
    }


@app.get("/items/{item_id}", response_model=Quote)
async def get_item(
    item_id: int = Path(ge=1, le=100),
    quantity: int = Query(default=1, ge=1, le=100),
    currency: Literal["EUR", "USD"] = "EUR",
):
    global requests
    requests += 1
    return quote(item_id, quantity, currency)


@app.post("/orders", response_model=Receipt)
async def create_order(order: Order):
    global requests
    requests += 1
    lines = [quote(line.item_id, line.quantity, "EUR") for line in order.items]
    subtotal = sum(line["total_cents"] for line in lines)
    discount = subtotal // 10 if order.coupon == "SAVE10" else 0
    return {
        "customer_id": order.customer_id, "lines": lines,
        "discount_cents": discount, "total_cents": subtotal - discount,
    }


@app.post("/proxy/{client}")
async def proxy(client: Literal["aiohttp", "httpx"], request: Request):
    global requests
    requests += 1
    body = await request.body()
    headers = {"Content-Type": "application/json"}
    if client == "aiohttp":
        async with request.app.state.aiohttp_client.post(
            UPSTREAM + "/echo", data=body, headers=headers,
        ) as response:
            result, status = await response.read(), response.status
    else:
        response = await request.app.state.httpx_client.post(
            UPSTREAM + "/echo", content=body, headers=headers,
        )
        result, status = response.content, response.status_code
    return Response(result, status_code=status, media_type="application/json")


@app.get("/__worker", include_in_schema=False)
async def worker():
    return {
        "pid": os.getpid(), "requests": requests,
        "loop": type(asyncio.get_running_loop()).__module__,
    }


ORDER_BODY = {
    "customer_id": 7, "items": [
        {"item_id": 42, "quantity": 3}, {"item_id": 7, "quantity": 2},
    ], "coupon": "SAVE10",
}
EXPECTED_LINES = [
    {"item_id": item_id, "name": f"Item {item_id}", "quantity": quantity,
     "currency": "EUR", "total_cents": total, "tags": ["catalog", "in-stock"]}
    for item_id, quantity, total in [(42, 3, 5010), (7, 2, 2640)]
]
CASES = {
    "get-item": {
        "path": "/items/42?quantity=3&currency=EUR", "body": None,
        "expected": EXPECTED_LINES[0],
    },
    "post-order": {
        "path": "/orders", "body": ORDER_BODY,
        "expected": {
            "customer_id": 7, "lines": EXPECTED_LINES,
            "discount_cents": 765, "total_cents": 6885,
        },
    },
}

for client in ("aiohttp", "httpx"):
    for size, length in (("1k", 1024), ("64k", 65536)):
        body = {"data": "x" * length}
        CASES[f"proxy-{client}-{size}"] = {
            "path": f"/proxy/{client}", "body": body, "expected": body,
        }
