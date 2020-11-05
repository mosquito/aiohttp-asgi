from aiohttp.web import Application


class ASGIAppWrapper:
    def __init__(self, app: Application):
        self._app = app

    async def __call__(self, scope, receive, send):
        pass
