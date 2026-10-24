# Command line server

The package installs the `aiohttp-asgi` command, which serves an ASGI
application without additional code. The same server starts with
`python -m aiohttp_asgi`.

```bash
aiohttp-asgi --address 127.0.0.1 --port 8080 test_app:application
```

The last argument names the application in the `module_name:attribute`
format. The command imports `module_name` from the current `sys.path`, so the
module must be importable from the working directory.

## Try an application without changes

The command needs no code change in the application, therefore it answers two
questions in one minute:

1. Does the application run on this adapter at all?
2. How fast does it answer here, against the current server?

Start the application which already exists:

```bash
aiohttp-asgi --address 127.0.0.1 --port 8080 myapp.asgi:application
```

Then walk through the paths which matter: a short answer, an upload, a
streaming answer, a WebSocket. A wrong answer or a traceback in the log shows
the part which the adapter does not serve, and the
[Limitations](limitations.md) page names the usual reasons.

For a measurement start the same application on both servers, on one port
each, and give both the same load:

```bash
# The current server.
uvicorn --host 127.0.0.1 --port 8001 myapp.asgi:application

# This adapter.
aiohttp-asgi --address 127.0.0.1 --port 8002 myapp.asgi:application

# The same load for each port.
oha -z 30s -c 100 http://127.0.0.1:8001/path
oha -z 30s -c 100 http://127.0.0.1:8002/path
```

Keep the conditions equal, because they decide the result: the same number of
processes (`--workers` here against `--workers` there), the same event loop,
the same CPU set for each server, and a warmup before the measurement.

:::{tip}
The adapter answers through the `aiohttp` server, therefore this measurement
also shows what a [hybrid application](hybrid.md) gives: the ASGI routes keep
the speed which this test shows, and a rewritten `aiohttp` handler answers
without the ASGI bridge.
:::

## Options

```{list-table}
:header-rows: 1
:widths: 30 70

* - Option
  - Meaning
* - `-a`, `--address`
  - Listen address. The default is `::1`. An address with a colon gives an
    IPv6 socket.
* - `-p`, `--port`
  - Listen port. The default is `8080`.
* - `--reuse-addr`
  - Set `SO_REUSEADDR` on the socket.
* - `--reuse-port`
  - Set `SO_REUSEPORT` on the socket, where the platform has it.
* - `--log-level`
  - One of `debug`, `info`, `warning`, `error`, `critical`. The default is
    `info`.
* - `--event-loop`
  - The event loop implementation. The choices are the installed loops, see
    [Event loop](#event-loop).
* - `-w`, `--workers`
  - Number of worker processes, see [Worker processes](#worker-processes).
    The option exists only where forklib is installed.
```

## Worker processes

One process uses one CPU core. The `-w/--workers` option starts more worker
processes:

```bash
aiohttp-asgi --workers 4 test_app:application
```

The parent process binds the listening socket first, and then
[forklib](https://github.com/mosquito/forklib) forks the workers. All workers
accept connections from that one shared socket, therefore the kernel
distributes the connections and no port needs a proxy in front.

- The parent process does not serve requests. It supervises the workers.
- `--workers 0` starts one worker for each CPU.
- Each worker imports the ASGI application after the fork. An application
  which starts threads or event loops on import therefore gets a correct
  process state.
- `SIGTERM` and `SIGINT` stop the parent and the workers.

The package requires forklib on Linux, so the option works there without an
additional step. On other POSIX systems install forklib:

```bash
pip install forklib
```

Windows has no `fork`, therefore the option does not exist there.

## Event loop

```bash
aiohttp-asgi --event-loop uvloop test_app:application
```

The command offers only the loops which the installation has, and `stdlib` is
always available:

```{list-table}
:header-rows: 1
:widths: 20 80

* - Choice
  - Event loop
* - `uvloop`
  - [uvloop](https://github.com/MagicStack/uvloop), the default when it is
    installed. Install it with `pip install "aiohttp-asgi[uvloop]"`.
* - `rloop`
  - [rloop](https://github.com/gi0baro/rloop), an event loop in Rust. Install
    it with `pip install "aiohttp-asgi[rloop]"`. It needs Python 3.10 or
    later.
* - `stdlib`
  - The asyncio event loop of the standard library.
```

Each worker creates the event loop after the fork, because a loop does not
survive a fork. The command therefore imports the loop module in the worker,
not in the parent.

## Signals and exit codes

The server answers until `SIGINT` or `SIGTERM` arrives. Then it closes the
listening socket, lets the running handlers finish, and exits with zero.

The exit code zero on a termination signal makes the command simple for
`systemd` and for a container:

```ini
[Service]
ExecStart=/usr/local/bin/aiohttp-asgi --address 0.0.0.0 --workers 4 app:application
Restart=on-failure
KillSignal=SIGTERM
```

## Lifespan events

The command does not send the ASGI lifespan events. An application which
needs `startup` or `shutdown` therefore runs through an `aiohttp` application
with {meth}`~aiohttp_asgi.ASGIResource.lifespan_mount`, see
[the resource page](aiohttp-application.md#send-the-lifespan-events).

## ASGI startup and shutdown

The CLI sends ASGI lifespan startup after the worker creates its event loop,
and shutdown when the runner stops. An application can create reusable
outbound HTTP client sessions in its lifespan context. Applications that do
not support lifespan can still serve HTTP requests.
