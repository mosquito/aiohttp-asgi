import asyncio
import logging
import typing as t
from contextlib import contextmanager

from aiohttp import ClientRequest, WSMsgType, hdrs
from aiohttp.abc import AbstractMatchInfo, AbstractStreamWriter
from aiohttp.web import (
    AbstractResource, Application, HTTPException, Request, StreamResponse,
    WebSocketResponse,
)
from yarl import URL


ASGIReceiveType = t.Callable[[], t.Awaitable[t.Dict[str, t.Any]]]
ASGISendType = t.Callable[[t.Dict[str, t.Any]], t.Any]
ASGIScopeType = t.Dict[str, t.Any]

ASGIApplicationType = t.Callable[
    [ASGIScopeType, ASGIReceiveType, ASGISendType],
    t.Any,
]


try:
    from aiohttp.web_urldispatcher import (
        _InfoDict as ResourceInfoDict,  # type: ignore
    )
except ImportError:
    ResourceInfoDict = t.Dict[str, t.Any]       # type: ignore


log = logging.getLogger(__name__)

_ApplicationColelctionType = t.Union[
    t.List[Application], t.Tuple[Application, ...],
]


class ASGIMatchInfo(AbstractMatchInfo):
    def __init__(self, handler: t.Callable[..., t.Any]):
        self._handler = handler
        self._apps = list()     # type: _ApplicationColelctionType
        self._current_app: t.Optional[Application] = None

    @property
    def handler(self) -> t.Callable[[Request], t.Awaitable[StreamResponse]]:
        return self._handler

    @property
    def expect_handler(self) -> t.Callable[[Request], t.Awaitable[None]]:
        raise NotImplementedError

    @property
    def http_exception(self) -> t.Optional[HTTPException]:
        return None

    @property
    def route(self):
        return None

    def get_info(self) -> t.Dict[str, t.Any]:
        return {}

    @property
    def apps(self) -> t.Tuple[Application, ...]:
        if not isinstance(self._apps, tuple):
            return tuple(self._apps)
        return self._apps

    def add_app(self, app: Application) -> None:
        if isinstance(self._apps, tuple):
            raise RuntimeError("Frozen resource")

        self._apps.append(app)

    def freeze(self) -> None:
        self._apps = tuple(self.apps)

    @contextmanager
    def set_current_app(
        self,
        app: Application,
    ) -> t.Generator[None, None, None]:
        prev = self._current_app
        self._current_app = app
        try:
            yield
        finally:
            self._current_app = prev


_ResponseType = t.Optional[t.Union[StreamResponse, WebSocketResponse]]
_WriterType = t.Optional[AbstractStreamWriter]


class ASGIContext:
    _ws_close_codes = frozenset((
        WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED, WSMsgType.ERROR,
    ))

    def __init__(
        self, app: t.Callable[..., t.Any],
        request: Request, root_path: str,
    ):
        self.request = request

        connection_hdr = request.headers.get("Connection", "").lower()
        self.http_version = "1.1" if connection_hdr == "keep-alive" else "1.0"
        self.app = app
        self.root_path = root_path.rstrip("/")
        self.start_response_event = asyncio.Event()
        self.ws_connect_event = asyncio.Event()
        self.response = None   # type: _ResponseType
        self.writer = None     # type: _WriterType
        self.task = None       # type: t.Optional[asyncio.Task]
        self.loop = asyncio.get_event_loop()

    def is_websocket(self):
        return (
            self.request.headers.get("Connection", "").lower() == "upgrade" and
            self.request.headers.get("Upgrade", "").lower() == "websocket"
        )

    @property
    def scope(self) -> dict:
        raw_path = self.request.raw_path

        result = {
            "type": "http",
            "http_version": self.http_version,
            "server": [self.request.url.host, self.request.url.port],
            "client": [self.request.remote, 0],
            "scheme": self.request.url.scheme,
            "method": self.request.method,
            "root_path": self.root_path,
            "path": self.request.path,
            "raw_path": raw_path.encode(),
            "query_string": self.request.query_string.encode(),
            "headers": [(k.lower(), v) for k, v in self.request.raw_headers],
        }

        if self.is_websocket():
            result["type"] = "websocket"
            result["scheme"] = "wss" if self.request.secure else "ws"
            result["subprotocols"] = []

        return result

    async def on_receive(self):
        if self.is_websocket():
            if not self.ws_connect_event.is_set():
                self.ws_connect_event.set()
                return {
                    "type": "websocket.connect",
                    "headers": tuple(self.request.raw_headers),
                }

            while True:
                msg = await self.response.receive()

                if msg.type in (WSMsgType.BINARY, WSMsgType.TEXT):
                    bytes_payload = None
                    str_payload = None

                    if msg.type == WSMsgType.BINARY:
                        bytes_payload = msg.data

                    if msg.type == WSMsgType.TEXT:
                        str_payload = msg.data

                    return {
                        "type": "websocket.receive",
                        "bytes": bytes_payload,
                        "text": str_payload,
                    }

                if msg.type in self._ws_close_codes:
                    self.start_response_event.set()
                    return {
                        "type": "websocket.disconnect",
                        "code": self.response.close_code,
                    }

        chunk, more_body = await self.request.content.readchunk()
        return {
            "type": "http.request",
            "body": chunk,
            "more_body": more_body,
        }

    async def on_send(self, payload: t.Dict[str, t.Any]):
        if payload["type"] == "http.response.start":
            if self.start_response_event.is_set():
                raise asyncio.InvalidStateError

            self.response = StreamResponse()
            self.response.set_status(payload["status"])

            for name, value in payload.get("headers", ()):
                header_name = name.title().decode()
                self.response.headers[header_name] = value.decode()

            if not self.response.headers.get(hdrs.CONTENT_LENGTH):
                self.response.enable_chunked_encoding()

            self.writer = await self.response.prepare(self.request)
            self.start_response_event.set()
            return

        if payload["type"] == "websocket.accept":
            if self.start_response_event.is_set():
                raise asyncio.InvalidStateError

            self.response = WebSocketResponse()
            self.writer = await self.response.prepare(self.request)
            return

        if payload["type"] == "http.response.body":
            if self.writer is None:
                raise TypeError("Unexpected message %r" % payload, payload)

            if payload.get("more_body", False):
                await self.writer.write(payload["body"])
                return

            await self.writer.write_eof(payload["body"])
            return

        if payload["type"] == "websocket.send":
            if (
                isinstance(self.response, WebSocketResponse) and
                self.response.closed
            ):
                raise TypeError("Unexpected message %r" % payload, payload)

            if not isinstance(self.response, WebSocketResponse):
                raise RuntimeError("Wrong response type")

            message_bytes = payload.get("bytes")
            message_text = payload.get("text")

            if not any((message_text, message_bytes)):
                raise TypeError(
                    "Exactly one of bytes or text must be non-None."
                    " One or both keys may be present, however.",
                )

            if message_bytes is not None:
                await self.response.send_bytes(message_bytes)

            if message_text is not None:
                await self.response.send_str(message_text)

            return

    async def get_response(self) -> t.Union[StreamResponse, WebSocketResponse]:
        await self.app(
            self.scope,
            self.on_receive,
            self.on_send,
        )

        if self.response is None:
            raise RuntimeError

        return self.response


class ASGIResource(AbstractResource):
    def __init__(
        self, app: ASGIApplicationType, root_path="/",
        name: str = None,
    ):
        super().__init__(name=name)
        self._root_path = root_path
        self._asgi_app = app

    def __iter__(self):
        return self

    def __next__(self):
        raise StopIteration

    def __len__(self):
        return 0

    @property
    def canonical(self) -> str:
        return "%s/{asgi path}" % (self._root_path.rstrip("/"),)

    def url_for(self, **kwargs: str) -> URL:
        return URL(self._root_path)

    def add_prefix(self, prefix: str) -> None:
        raise NotImplementedError

    def get_info(self) -> ResourceInfoDict:
        raise NotImplementedError

    def raw_match(self, path: str) -> bool:
        return path.startswith(self._root_path)

    async def resolve(self, request: Request):
        if not self.raw_match(request.path):
            return None, set()

        return (
            ASGIMatchInfo(self._handle),
            ClientRequest.ALL_METHODS,
        )

    async def _handle(self, request: Request) -> StreamResponse:
        ctx = ASGIContext(self._asgi_app, request, self._root_path)
        return await ctx.get_response()

    @property
    def lifespan_scope(self) -> dict:
        return {
            "type": "lifespan",
            "asgi": {
                "version": "3.0",
                "spec_version": "1.0",
            },
        }

    def lifespan_mount(self, app: Application, startup=True, shutdown=False):
        receives = asyncio.Queue()      # type: asyncio.Queue
        sends = asyncio.Queue()         # type: asyncio.Queue

        async def on_startup(_):
            receives.put_nowait({"type": "lifespan.startup"})
            while True:
                msg = await sends.get()
                if msg["type"] == "lifespan.startup.complete":
                    return

                if msg["type"] == "lifespan.startup.failed":
                    log.error(
                        "ASGI application %r shutdown failed: %s",
                        self._asgi_app, msg["message"],
                    )
                    return

        if startup:
            app.on_startup.append(on_startup)

        task = asyncio.get_event_loop().create_task(
            self._asgi_app(self.lifespan_scope, receives.get, sends.put),
        )

        async def on_shutdown(_):
            receives.put_nowait({"type": "lifespan.shutdown"})

            while True:
                msg = await sends.get()
                if msg["type"] == "lifespan.shutdown.complete":
                    await task
                    return

                if msg["type"] == "lifespan.shutdown.failed":
                    log.error(
                        "ASGI application %r shutdown failed: %s",
                        self._asgi_app, msg["message"],
                    )
                    await task
                    return

        if shutdown:
            app.on_shutdown.append(on_shutdown)
        else:
            app.on_shutdown.append(lambda _: task)
