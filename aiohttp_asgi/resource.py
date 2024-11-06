import asyncio
import logging
from contextlib import contextmanager
from typing import (
    Any, Awaitable, Callable, Coroutine, Dict, Generator, List, MutableMapping,
    Optional, Set, Tuple, Union,
)

from aiohttp import ClientRequest, WSMessage, WSMsgType, hdrs
from aiohttp.abc import AbstractMatchInfo, AbstractStreamWriter
from aiohttp.helpers import DEBUG
from aiohttp.web import (
    AbstractResource, Application, HTTPException, Request, StreamResponse,
    WebSocketResponse,
)
from urllib.parse import unquote
from yarl import URL


try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict


ASGIScopeType = MutableMapping[str, Any]
ASGIReceiveType = Callable[[], Awaitable[MutableMapping[str, Any]]]
ASGISendType = Callable[[MutableMapping[str, Any]], Any]

ASGIApplicationType = Callable[
    [ASGIScopeType, ASGIReceiveType, ASGISendType],
    Coroutine[Any, Any, Any],
]


try:
    from aiohttp.web_urldispatcher import (
        _InfoDict as ResourceInfoDict,  # type: ignore
    )
except ImportError:
    ResourceInfoDict = Dict[str, Any]      # type: ignore


log = logging.getLogger(__name__)

_ApplicationColelctionType = Union[
    List[Application], Tuple[Application, ...],
]


class ScopeDict(TypedDict):
    type: str
    http_version: str
    server: List[Union[str, int, None]]
    client: List[Union[str, int, None]]
    scheme: str
    method: str
    root_path: str
    path: str
    raw_path: bytes
    query_string: bytes
    headers: List[Tuple[bytes, bytes]]
    subprotocols: Optional[List[str]]


class ASGIDict(TypedDict):
    version: str
    spec_version: str


class LifespanDict(TypedDict):
    type: str
    asgi: ASGIDict


class ASGIMatchInfo(AbstractMatchInfo):
    def __init__(self, handler: Callable[..., Any]):
        self._handler = handler
        self._apps = list()     # type: _ApplicationColelctionType
        self._current_app: Optional[Application] = None
        self._frozen = False

    @property
    def handler(self) -> Callable[[Request], Awaitable[StreamResponse]]:
        return self._handler

    @property
    def expect_handler(self) -> Callable[[Request], Awaitable[None]]:
        raise NotImplementedError

    @property
    def http_exception(self) -> Optional[HTTPException]:
        return None

    @property
    def route(self) -> None:
        return None

    def get_info(self) -> Dict[str, Any]:
        return {}

    @property
    def apps(self) -> Tuple[Application, ...]:
        if not isinstance(self._apps, tuple):
            return tuple(self._apps)
        return self._apps

    @property
    def apps(self) -> Tuple["Application", ...]:
        return tuple(self._apps)

    def add_app(self, app: "Application") -> None:
        if self._frozen:
            raise RuntimeError("Cannot change apps stack after .freeze() call")
        if self._current_app is None:
            self._current_app = app
        self._apps.insert(0, app)

    # @contextmanager
    # def set_current_app(
    #     self,
    #     app: Application,
    # ) -> Generator[None, None, None]:
    #     prev = self._current_app
    #     self._current_app = app
    #     try:
    #         yield
    #     finally:
    #         self._current_app = prev

    @property
    def current_app(self) -> "Application":
        app = self._current_app
        assert app is not None
        return app

    @current_app.setter
    def current_app(self, app: "Application") -> None:
        if DEBUG:  # pragma: no cover
            if app not in self._apps:
                raise RuntimeError(
                    "Expected one of the following apps {!r}, got {!r}".format(
                        self._apps, app
                    )
                )
        self._current_app = app

    def freeze(self) -> None:
        self._frozen = True

_ResponseType = Optional[Union[StreamResponse, WebSocketResponse]]
_WriterType = Optional[AbstractStreamWriter]


class ASGIContext:
    _ws_close_codes = frozenset((
        WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED, WSMsgType.ERROR,
    ))

    def __init__(
        self, app: Callable[..., Any],
        request: Request, root_path: str,
    ):
        self.request = request

        connection_hdr = request.headers.get("Connection", "").lower()
        self.http_version = "1.1" if connection_hdr == "keep-alive" else "1.0"
        self.app = app
        self.root_path = root_path.rstrip("/")
        self.start_response_event = asyncio.Event()
        self.ws_connect_event = asyncio.Event()
        self.response: _ResponseType = None
        self.writer: _WriterType = None
        self.task: Optional[asyncio.Task] = None
        self.loop = asyncio.get_event_loop()

    def is_websocket(self) -> bool:
        return (
            self.request.headers.get("Connection", "").lower() == "upgrade" and
            self.request.headers.get("Upgrade", "").lower() == "websocket"
        )

    @property
    def scope(self) -> ScopeDict:
        raw_path = self.request.raw_path

        result = ScopeDict(
            type="http",
            http_version=self.http_version,
            server=[self.request.url.host, self.request.url.port],
            client=[self.request.remote, 0],
            scheme=self.request.url.scheme,
            method=self.request.method,
            root_path=self.root_path,
            path=self.request.path,
            raw_path=raw_path.encode(),
            query_string=self.request.query_string.encode(),
            headers=[(k.lower(), v) for k, v in self.request.raw_headers],
            subprotocols=None,
        )

        if self.is_websocket():
            result["type"] = "websocket"
            result["scheme"] = "wss" if self.request.secure else "ws"

            # Decode websocket subprotocol options
            subprotocols = []
            for header, value in result["headers"]:
                if header == b"sec-websocket-protocol":
                    subprotocols = [
                        x.strip() for x in unquote(value.decode("ascii")).split(",")
                    ]
            result["subprotocols"] = subprotocols

        return result

    async def on_receive(self) -> Dict[str, Any]:
        if self.is_websocket():
            if not self.ws_connect_event.is_set():
                self.ws_connect_event.set()
                return {
                    "type": "websocket.connect",
                    "headers": tuple(self.request.raw_headers),
                }

            assert isinstance(self.response, WebSocketResponse)
            response: WebSocketResponse = self.response

            while True:
                msg: WSMessage = await response.receive()

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
                        "code": response.close_code,
                    }

        chunk, _ = await self.request.content.readchunk()
        return {
            "type": "http.request",
            "body": chunk,
            "more_body": not self.request.content.at_eof(),
        }

    async def on_send(self, payload: Dict[str, Any]) -> None:
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

            self.response = WebSocketResponse(protocols=self.scope["subprotocols"])
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

    async def get_response(self) -> Union[StreamResponse, WebSocketResponse]:
        await self.app(
            self.scope,
            self.on_receive,
            self.on_send,
        )

        if self.response is None:
            raise RuntimeError

        return self.response


class ASGIResource(AbstractResource):
    SHUTDOWN_TIMEOUT = 60

    def __init__(
        self, app: ASGIApplicationType, root_path: str = "/",
        name: Optional[str] = None,
    ):
        super().__init__(name=name)
        self._root_path = root_path
        self._asgi_app = app

    def __iter__(self) -> Any:
        return self

    def __next__(self) -> Any:
        raise StopIteration

    def __len__(self) -> int:
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

    async def resolve(
        self, request: Request,
    ) -> Tuple[Optional[ASGIMatchInfo], Set[str]]:
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
    def lifespan_scope(self) -> LifespanDict:
        return LifespanDict(
            type="lifespan",
            asgi=ASGIDict(version="3.0", spec_version="1.0"),
        )

    def lifespan_mount(self, app: Application) -> None:
        async def lifespan(_: Any) -> Any:
            loop = asyncio.get_event_loop()
            receives: asyncio.Queue = asyncio.Queue()
            sends: asyncio.Queue = asyncio.Queue()

            await receives.put({"type": "lifespan.startup"})

            asgi_lifespan_task: asyncio.Task = loop.create_task(
                self._asgi_app(
                    self.lifespan_scope,        # type: ignore
                    receives.get,
                    sends.put,
                ),
            )

            while True:
                msg = await sends.get()
                if msg["type"] == "lifespan.startup.complete":
                    log.info(
                        "ASGI application %r startup completed.",
                        self._asgi_app,
                    )
                    break
                elif msg["type"] == "lifespan.startup.failed":
                    log.error(
                        "ASGI application %r startup failed: %s",
                        self._asgi_app, msg["message"],
                    )
                    break
                else:
                    log.error("Unexpected ASGI message when startup: %r", msg)
                    break

            yield

            await receives.put({"type": "lifespan.shutdown"})

            if asgi_lifespan_task.done():
                asgi_lifespan_task = loop.create_task(
                    self._asgi_app(
                        self.lifespan_scope,    # type: ignore
                        receives.get,
                        sends.put,
                    ),
                )

            while True:
                msg = await sends.get()
                if msg["type"] == "lifespan.shutdown.complete":
                    log.info(
                        "ASGI application %r shutdown completed.",
                        self._asgi_app,
                    )
                    break
                elif msg["type"] == "lifespan.shutdown.failed":
                    log.error(
                        "ASGI application %r shutdown failed: %s",
                        self._asgi_app, msg["message"],
                    )
                    break
                else:
                    log.error("Unexpected ASGI message when shutdown: %r", msg)
                    break

            await asyncio.wait_for(
                asgi_lifespan_task, timeout=self.SHUTDOWN_TIMEOUT,
            )

        app.cleanup_ctx.append(lifespan)
