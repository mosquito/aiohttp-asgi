import asyncio
import logging
from typing import Dict, Any, Optional, Tuple, Callable, Awaitable

from aiohttp import ClientRequest, WSMsgType
from aiohttp.abc import AbstractMatchInfo
from aiohttp.web import Request, StreamResponse
from aiohttp.web_app import Application
from aiohttp.web_exceptions import HTTPException
from aiohttp.web_urldispatcher import AbstractResource
from aiohttp.web_ws import WebSocketResponse
from yarl import URL


log = logging.getLogger(__name__)


class ASGIMatchInfo(AbstractMatchInfo):
    def __init__(self, handler):
        self._handler = handler
        self._apps = list()

    @property
    def handler(self) -> Callable[[Request], Awaitable[StreamResponse]]:
        return self._handler

    @property
    def expect_handler(self) -> Callable[[Request], Awaitable[None]]:
        raise NotImplementedError

    @property
    def http_exception(self) -> Optional[HTTPException]:
        raise None

    def get_info(self) -> Dict[str, Any]:
        return {}

    @property
    def apps(self) -> Tuple[Application, ...]:
        if isinstance(self._apps, list):
            return tuple(self._apps)
        return self._apps

    def add_app(self, app: Application) -> None:
        if isinstance(self._apps, tuple):
            raise RuntimeError("Frozen resource")

        self._apps.append(app)

    def freeze(self) -> None:
        self._apps = tuple(self.apps)


class ASGIContext:
    def __init__(self, app, request: Request, root_path: str):
        self.request = request
        self.app = app
        self.root_path = root_path.rstrip("/")
        self.start_response_event = asyncio.Event()
        self.response = None        # type: Optional[StreamResponse]
        self.writer = None
        self.task = None
        self.loop = asyncio.get_event_loop()

    def is_webscoket(self):
        return (
            self.request.headers.get('Connection', '').lower() == 'upgrade' and
            self.request.headers.get('Upgrade', '').lower() == 'websocket'
        )

    @property
    def scope(self) -> dict:
        raw_path = self.request.raw_path

        result = {
            "type": "http",
            "http_version": "1.1",
            "server": [self.request.url.host, self.request.url.port],
            "client": [self.request.remote, 0],
            "scheme": self.request.url.scheme,
            "method": self.request.method,
            "root_path": self.root_path,
            "path": self.request.path,
            "raw_path": raw_path.encode(),
            "query_string": self.request.query_string.encode(),
            "headers": [hdr for hdr in self.request.raw_headers],
        }

        if self.is_webscoket():
            result["type"] = "websocket"
            result["scheme"] = "wss" if self.request.secure else "wss"
            result["subprotocols"] = []

        return result

    async def on_receive(self):
        if self.is_webscoket():
            while True:
                msg = await self.response.receive()

                if msg.type in (WSMsgType.BINARY, WSMsgType.TEXT):
                    bytes_payload = None
                    str_payload = None

                    if msg.type == WSMsgType.BINARY:
                        bytes_payload = msg.data

                    if msg.type == WSMsgType.TEXT:
                        str_payload = msg.data.decode()

                    return {
                        "type": "websocket.receive",
                        "bytes": bytes_payload,
                        "text": str_payload,
                    }

                if msg.type == WSMsgType.CLOSE:
                    return {
                        "type": "websocket.close",
                        "code": 1000,
                    }

                continue

        chunk, more_body = await self.request.content.readchunk()
        return {
            "type": "http.request",
            "body": chunk,
            "more_body": more_body,
        }

    async def on_send(self, payload):
        if payload['type'] == 'http.response.start':
            if self.start_response_event.is_set():
                raise asyncio.InvalidStateError

            self.response = StreamResponse()
            self.response.set_status(payload['status'])

            for name, value in payload.get('headers', ()):
                header_name = name.title().decode()
                self.response.headers[header_name] = value.decode()

            self.writer = await self.response.prepare(self.request)
            self.start_response_event.set()
            return

        if payload['type'] == 'websocket.accept':
            if self.start_response_event.is_set():
                raise asyncio.InvalidStateError

            self.response = WebSocketResponse()
            await self.response.prepare(self.request)
            self.start_response_event.set()
            self.writer = None
            return

        if payload['type'] == 'http.response.body':
            if self.writer is None:
                raise TypeError("Unexpected message %r" % payload, payload)

            await self.writer.write(payload['body'])
            # receive_queue.put_nowait({"type": "http.disconnect"})

            if payload.get('more_body', False):
                await self.writer.write_eof()
            return

        if payload['type'] == 'websocket.send':
            if self.writer is not None:
                raise TypeError("Unexpected message %r" % payload, payload)

            message_bytes = payload.get('bytes')
            message_text = payload.get('text')

            if not any((message_text, message_bytes)):
                raise TypeError('Exactly one of bytes or text must be non-None.'
                                ' One or both keys may be present, however.')

            if message_bytes is not None:
                await self.response.send_bytes(message_bytes)

            if message_text is not None:
                await self.response.send_str(message_text)

            return

    async def get_response(self) -> StreamResponse:
        self.task = self.loop.create_task(
            self.app(
                self.scope,
                self.on_receive,
                self.on_send
            )
        )

        await self.start_response_event.wait()
        return self.response


class ASGIResource(AbstractResource):
    def __init__(self, app, root_path="/", name=None):
        super().__init__(name=name)
        self._root_path = root_path
        self._asgi_app = app

    def __iter__(self):
        raise StopIteration

    def __len__(self):
        return 0

    @property
    def canonical(self) -> str:
        return "%s/{asgi path}" % (self._root_path.rstip("/"),)

    def url_for(self, **kwargs: str) -> URL:
        return URL(self._root_path)

    def add_prefix(self, prefix: str) -> None:
        raise NotImplementedError

    def get_info(self) -> Dict[str, Any]:
        raise NotImplementedError

    def raw_match(self, path: str) -> bool:
        return path.startswith(self._root_path)

    async def resolve(self, request: Request):
        if not self.raw_match(request.path):
            return None, set()

        return (
            ASGIMatchInfo(self._handle),
            ClientRequest.ALL_METHODS
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
            }
        }

    def lifespan_mount(self, app: Application, startup=True, shutdown=False):
        receives = asyncio.Queue()
        sends = asyncio.Queue()

        async def on_startup(_):
            receives.put_nowait({"type": "lifespan.startup"})
            while True:
                msg = await sends.get()
                if msg['type'] == "lifespan.startup.complete":
                    return

                if msg['type'] == "lifespan.startup.failed":
                    log.error(
                        "ASGI application %r shutdown failed: %s",
                        self._asgi_app, msg['message']
                    )
                    return

        if startup:
            app.on_startup.append(on_startup)

        task = asyncio.get_event_loop().create_task(
            self._asgi_app(self.lifespan_scope, receives.get, sends.put)
        )

        async def on_shutdown(_):
            receives.put_nowait({"type": "lifespan.shutdown"})

            while True:
                msg = await sends.get()
                if msg['type'] == "lifespan.shutdown.complete":
                    await task
                    return

                if msg['type'] == "lifespan.shutdown.failed":
                    log.error(
                        "ASGI application %r shutdown failed: %s",
                        self._asgi_app, msg['message']
                    )
                    await task
                    return

        if shutdown:
            app.on_shutdown.append(on_shutdown)
        else:
            app.on_shutdown.append(lambda _: task)
