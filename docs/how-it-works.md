# How it works

The adapter has three parts: a resource for the `aiohttp` router, a match info
which the router returns, and a context which bridges one request.

```{list-table}
:header-rows: 1
:widths: 30 70

* - Part
  - Task
* - {class}`~aiohttp_asgi.ASGIResource`
  - Matches the request path, builds the match info, mounts the lifespan
* - `ASGIMatchInfo`
  - Gives the handler, the application stack and the expect handler to
    `aiohttp`
* - `ASGIContext`
  - Builds the ASGI scope, moves the body in both directions, makes the
    `aiohttp` response
```

## The request path

1. The `aiohttp` router asks each resource. `ASGIResource.raw_match()` accepts
   the path when it starts with `root_path`, and `resolve()` then returns a
   match info for every HTTP method.
2. `aiohttp` calls the handler of the match info. The handler creates an
   `ASGIContext` for this request.
3. The context builds the scope from the request, and calls the ASGI
   application with its `receive` and `send` functions.
4. The application reads the body through `receive`, and writes the answer
   through `send`.
5. The context returns the prepared `aiohttp` response to the server.

## The request body

The context reads the body in chunks and gives each chunk to the application
as an `http.request` message:

- `body` holds the chunk.
- `more_body` is `True` while the body continues.

An application therefore streams a large upload without the whole body in
memory. A request with the `Expect: 100-continue` header gets `100 Continue`
before the body arrives, and an unknown `Expect` value gives 417.

## The response

The application sends two kinds of messages:

- `http.response.start` carries the status and the headers. The context
  creates the `aiohttp` `StreamResponse` and prepares it.
- `http.response.body` carries a chunk. The context writes the chunk, and
  `more_body` says whether more chunks follow.

The answer therefore streams to the client while the application works.

## WebSockets

The context sees a WebSocket handshake, and then:

- `scope["type"]` is `websocket`, and `scope["scheme"]` is `ws` or `wss`.
- The first `receive` call gives `websocket.connect` with the request headers.
- `websocket.accept` makes the `aiohttp` `WebSocketResponse` and prepares it
  with the subprotocols from the scope.
- `websocket.send` writes a text or a binary message.
- A message from the client becomes `websocket.receive`, with `text` or
  `bytes`. A close or an error becomes `websocket.disconnect` with the close
  code.

## The lifespan

{meth}`~aiohttp_asgi.ASGIResource.lifespan_mount` appends a cleanup context to
the `aiohttp` application. The context:

1. Puts `lifespan.startup` in the receive queue, and starts the ASGI
   application as a task with the lifespan scope.
2. Waits for `lifespan.startup.complete`, and logs a failed startup.
3. Gives the control back to `aiohttp`, which then serves the requests.
4. Puts `lifespan.shutdown` when the `aiohttp` application stops, waits for
   `lifespan.shutdown.complete`, and then waits at most
   {attr}`~aiohttp_asgi.ASGIResource.SHUTDOWN_TIMEOUT` seconds for the
   lifespan task.

## The command line server

The command does the same work around the resource:

1. It checks the format of the `module:attribute` argument, but it does not
   import the module.
2. It binds the listening socket.
3. With more than one worker it forks the workers from the parent, so the
   workers share the socket.
4. Each worker imports the application, creates the event loop, registers the
   resource in a new `aiohttp` application and serves the socket.
5. A signal sets a stop event, and the worker then closes the server.

The import after the fork and the event loop after the fork keep the state of
each worker correct, because a thread or an event loop from the parent does
not work in a forked process.
