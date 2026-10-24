"""Run Daphne workers on one inherited listening socket via forklib."""

from functools import partial
import os
from pathlib import Path
import sys

import forklib

from aiohttp_asgi.__main__ import bind_socket


def serve(application, descriptor):
    executable = str(Path(sys.executable).parent / "daphne")
    os.execv(executable, [
        executable, "--fd", str(descriptor), "--verbosity", "0",
        "--access-log", "/dev/null", application,
    ])


if __name__ == "__main__":
    with bind_socket(address="127.0.0.1", port=18080) as sock:
        sock.listen(1024)
        sock.set_inheritable(True)
        forklib.fork(
            int(sys.argv[1]), partial(serve, sys.argv[2], sock.fileno()),
        )
