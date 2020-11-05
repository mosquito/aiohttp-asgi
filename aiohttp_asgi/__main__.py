import importlib
import logging
import socket
from argparse import ArgumentParser, ArgumentTypeError

import aiohttp.web

from aiohttp_asgi import ASGIResource


parser = ArgumentParser(prog="aiohttp-asgi")
group = parser.add_argument_group("HTTP options")
group.add_argument("-a", "--address", help="Listen address", default="::1")
group.add_argument("-p", "--port", help="Listen port", default=8080)
group.add_argument("--reuse-addr", action="store_true")
group.add_argument("--reuse-port", action="store_true")


parser.add_argument(
    "--log-level", default="info", choices=[
        "debug", "info", "warning", "error", "critical",
    ],
)


def parse_app(app):
    try:
        module_name, asgi_app = app.split(":", 1)
    except ValueError:
        raise ArgumentTypeError(
            "Should like \"module_name:asgi_application\" not %r" % (app,),
        )

    try:
        module = importlib.import_module(module_name)
    except ImportError:
        raise ArgumentTypeError("Can not import module %r" % (module_name,))

    return getattr(module, asgi_app)


parser.add_argument(
    "application", help="ASGI application module",
    type=parse_app,
)


log = logging.getLogger()


def bind_socket(
    *args, address: str, port: int,
    reuse_addr: bool = True, reuse_port: bool = False
):
    if not args:
        if ":" in address:
            args = (socket.AF_INET6, socket.SOCK_STREAM)
        else:
            args = (socket.AF_INET, socket.SOCK_STREAM)

    sock = socket.socket(*args)
    sock.setblocking(False)

    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, int(reuse_addr))
    if hasattr(socket, "SO_REUSEPORT"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, int(reuse_port))
    else:
        log.warning("SO_REUSEPORT is not implemented by underlying library.")

    sock.bind((address, port))
    sock_addr = sock.getsockname()[:2]

    if sock.family == socket.AF_INET6:
        log.info("Listening http://[%s]:%s", *sock_addr)
    else:
        log.info("Listening http://%s:%s", *sock_addr)

    return sock


def main():
    arguments = parser.parse_args()
    logging.basicConfig(level=getattr(logging, arguments.log_level.upper()))

    app = aiohttp.web.Application()
    app.router.register_resource(ASGIResource(arguments.application))

    with bind_socket(
            address=arguments.address,
            port=arguments.port,
            reuse_addr=arguments.reuse_addr,
            reuse_port=arguments.reuse_port,
    ) as sock:
        aiohttp.web.run_app(app, sock=sock, print=log.debug)


if __name__ == "__main__":
    main()
