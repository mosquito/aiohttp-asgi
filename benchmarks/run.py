"""Compare FastAPI server CLIs with oha load and aiohttp latency samples."""

import argparse
from contextlib import ExitStack, contextmanager, suppress
from functools import partial
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import random
import shlex
import signal
import socket
import subprocess
import sys
import time
from urllib.request import Request, urlopen

from benchmarks.fastapi_app import CASES
from benchmarks.latency import client_probe

URL = "http://127.0.0.1:18080"
APP = "benchmarks.fastapi_app:app"
BIN = Path(sys.executable).parent
SERVERS = {
    **{f"aiohttp-asgi-{name}":
       f"aiohttp-asgi -a 127.0.0.1 -p 18080 --reuse-addr --event-loop {loop}"
       for name, loop in [("asyncio", "stdlib"), ("uvloop", "uvloop"),
                          ("rloop", "rloop")]},
    **{f"uvicorn-{name}":
       f"uvicorn --port 18080 --no-access-log --loop {loop} --http {http}"
       for name, loop, http in [("h11", "asyncio", "h11"),
                                ("httptools", "uvloop", "httptools"),
                                ("rloop", "rloop:new_event_loop",
                                 "httptools")]},
    **{f"hypercorn-{loop}":
       f"hypercorn --bind 127.0.0.1:18080 --worker-class {loop}"
       for loop in ["asyncio", "uvloop"]},
    **{name: "granian --interface asgi --port 18080 --runtime-threads 1 "
       f"--loop {loop} --http 1 --no-access-log"
       for name, loop in [("granian", "uvloop"), ("granian-rloop", "rloop")]},
    "anycorn": "anycorn --bind 127.0.0.1:18080",
    "daphne": "daphne -b 127.0.0.1 -p 18080 "
              "--verbosity 0 --access-log /dev/null",
    "gunicorn-asgi": "gunicorn --bind 127.0.0.1:18080 --worker-class asgi "
                     "--asgi-loop uvloop --no-control-socket",
    "gunicorn-uvicorn": "gunicorn --bind 127.0.0.1:18080 --no-control-socket "
                        "--worker-class uvicorn_worker.UvicornWorker",
}


def check_responses(cases):
    sizes = {}
    for name, case in cases.items():
        body = json.dumps(case["body"]).encode() if case["body"] else None
        request = Request(URL + case["path"], data=body,
                          headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=5) as response:
            received = response.read()
            assert response.status == 200
            assert json.loads(received) == case["expected"], name
            sizes[name] = len(received)
    return sizes


def worker_snapshot(workers, allowed_cpus, url=URL):
    found = {}
    deadline = time.monotonic() + 15
    while len(found) < workers and time.monotonic() < deadline:
        with urlopen(url + "/__worker", timeout=2) as response:
            worker = json.load(response)
        pid = worker["pid"]
        worker["affinities"] = {
            task.name: sorted(os.sched_getaffinity(int(task.name)))
            for task in Path(f"/proc/{pid}/task").iterdir()
        }
        assert all(set(cpus) <= allowed_cpus
                   for cpus in worker["affinities"].values())
        found[pid] = worker
    assert len(found) == workers, found
    return found


@contextmanager
def running_server(command, log_path, ready_url=URL + "/items/42"):
    with log_path.open("w") as log:
        process = subprocess.Popen(command, stdout=log, stderr=log,
                                   start_new_session=True)
        try:
            for _ in range(150):
                assert process.poll() is None, f"server exited: {log_path}"
                try:
                    with urlopen(ready_url, timeout=1):
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError(f"server did not start: {log_path}")
            yield
        finally:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()


def measure_case(case, url, path, payload, cpus, duration, snapshot, benchmark, size):
    concurrency = benchmark["concurrency"]
    client = client_probe(url, case["body"], concurrency, cpus, size,
                          path.with_suffix(".jsonl"))
    load = ["taskset", "-c", cpus, "oha", "--no-tui", "--output-format", "json",
            "--http-version", "1.1", "--disable-compression", "-w", "-t", "5s",
            "--worker-threads", "4", "-c", str(concurrency)]
    if payload is not None:
        load += ["-m", "POST", "-D", str(payload), "-T", "application/json"]
    load.append(url)
    subprocess.run([*load, "-z", "1s"], check=True, stdout=subprocess.DEVNULL)
    before = snapshot()
    measured = [*load, "-z", f"{duration}s"]
    data = json.loads(subprocess.check_output(measured))
    after = snapshot()
    assert set(before) == set(after), "workers restarted"
    delta = sum(after[p]["requests"] - before[p]["requests"] for p in before)
    data.update(client=client, benchmark={**benchmark,
                "command": shlex.join(measured), "server_requests": delta})
    path.write_text(json.dumps(data, indent=2))
    assert not data["errorDistribution"], path
    assert set(data["statusCodeDistribution"]) == {"200"}, path
    assert delta == data["statusCodeDistribution"]["200"], path
    assert data["summary"]["sizePerRequest"] == size, path
    print(path.name, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=int, default=5)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--concurrency", type=int, nargs="+", default=[100])
    parser.add_argument("--servers", nargs="+", choices=SERVERS,
                        default=None)
    parser.add_argument("--workloads", nargs="+", choices=CASES, default=list(CASES))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    if min(args.duration, args.repeats, args.workers, *args.concurrency) < 1:
        parser.error("duration, repeats, workers and concurrency must be > 0")
    cases = {name: CASES[name] for name in args.workloads}
    proxy = any(name.startswith("proxy-") for name in cases)
    excluded = {}
    if args.servers is None:
        args.servers = list(SERVERS)
        if proxy:
            args.servers.remove("daphne")
            excluded["daphne"] = "No ASGI lifespan for shared proxy sessions"
            print("Skipping Daphne proxy: no ASGI lifespan", flush=True)
    elif proxy and "daphne" in args.servers:
        parser.error("Daphne has no ASGI lifespan; select REST workloads only")
    cpus = sorted(os.sched_getaffinity(0))
    extra = 9 if proxy else 5
    if len(cpus) < args.workers + extra:
        parser.error(f"need workers + {extra} available CPUs")
    server_cpus = set(cpus[1:args.workers + 1])
    server_cpu = ",".join(map(str, sorted(server_cpus)))
    client_cpus = ",".join(map(str, cpus[-4:]))
    servers = {}
    for name in args.servers:
        command = shlex.split(SERVERS[name])
        command[0] = str(BIN / command[0])
        if name != "daphne":
            command += ["--workers", str(args.workers),
                        "--log-level", "warning"]
        elif args.workers > 1:
            command = [sys.executable, "-m", "benchmarks.daphne_server",
                       str(args.workers)]
        servers[name] = [*command, APP]
    for port in ([18080, 18081] if proxy else [18080]):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))
    args.output.mkdir(parents=True, exist_ok=False)
    payloads = {}
    for name, case in cases.items():
        payloads[name] = None
        if case["body"] is not None:
            payloads[name] = args.output / f"{name}.body"
            payloads[name].write_text(json.dumps(case["body"]))
    metadata = {
        "python": sys.version, "platform": platform.platform(),
        "cpu": Path("/proc/cpuinfo").read_text().splitlines(),
        "server_cpu": server_cpu, "client_cpus": client_cpus,
        "duration_seconds": args.duration, "repeats": args.repeats,
        "revision": args.revision, "workers": args.workers,
        "application": APP, "workloads": list(cases),
        "concurrency": args.concurrency, "seed": 42, "servers": servers,
        "excluded": excluded,
        "oha": subprocess.check_output(["oha", "--version"], text=True),
        "packages": sorted(f"{d.metadata['Name']}=={d.version}"
                           for d in importlib.metadata.distributions()),
        "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with ExitStack() as stack:
        if proxy:
            backend_url = "http://127.0.0.1:18081"
            backend_cpus = set(cpus[args.workers + 1:args.workers + 5])
            backend_cpu = ",".join(map(str, sorted(backend_cpus)))
            command = ["taskset", "-c", backend_cpu, sys.executable,
                       "-m", "benchmarks.echo_server", "4"]
            os.environ["BENCHMARK_UPSTREAM"] = backend_url
            metadata["upstream"] = {"url": backend_url, "workers": 4,
                                    "cpus": backend_cpu, "command": command}
            stack.enter_context(running_server(
                command, args.output / "echo.log", backend_url + "/__worker",
            ))
            backend_snapshot = partial(worker_snapshot, 4, backend_cpus, backend_url)
            (args.output / "echo-workers.json").write_text(json.dumps(backend_snapshot()))
            direct = {}
            for name in cases:
                if name.startswith("proxy-"):
                    direct.setdefault("echo-" + name.rsplit("-", 1)[1], name)
            directory = args.output / "backend"
            directory.mkdir()
            (directory / "metadata.json").write_text(json.dumps({
                **metadata, "servers": {"echo": command}, "workloads": list(direct),
                "application": "benchmarks.echo_server:create_app",
                "server_cpu": backend_cpu, "workers": 4,
            }, indent=2))
            for repeat in range(args.repeats):
                for workload, name in direct.items():
                    case = cases[name]
                    with urlopen(Request(backend_url + "/echo",
                                         data=payloads[name].read_bytes(),
                                         headers={"Content-Type": "application/json"}),
                                 timeout=5) as response:
                        content = response.read()
                        assert json.loads(content) == case["expected"]
                    for concurrency in args.concurrency:
                        path = directory / f"echo-r{repeat + 1}-{workload}-c{concurrency}.json"
                        measure_case(
                            case, backend_url + "/echo", path, payloads[name],
                            client_cpus, args.duration, backend_snapshot,
                            {"server": "echo", "workload": workload,
                             "concurrency": concurrency, "repeat": repeat + 1},
                            len(content),
                        )
        (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2))
        rng = random.Random(42)
        for repeat in range(args.repeats):
            names = list(servers)
            rng.shuffle(names)
            for name in names:
                prefix = args.output / f"{name}-r{repeat + 1}"
                with running_server(["taskset", "-c", server_cpu, *servers[name]],
                                    prefix.with_suffix(".log")):
                    sizes = check_responses(cases)
                    snapshot = worker_snapshot(args.workers, server_cpus)
                    Path(f"{prefix}-workers.json").write_text(json.dumps(snapshot))
                    matrix = [(w, c) for w in args.workloads for c in args.concurrency]
                    rng.shuffle(matrix)
                    for workload, concurrency in matrix:
                        path = Path(f"{prefix}-{workload}-c{concurrency}.json")
                        url = URL + CASES[workload]["path"]
                        measure_case(
                            CASES[workload], url, path, payloads[workload],
                            client_cpus, args.duration,
                            partial(worker_snapshot, args.workers, server_cpus),
                            {"server": name, "workload": workload,
                             "concurrency": concurrency, "repeat": repeat + 1},
                            sizes[workload],
                        )


if __name__ == "__main__":
    main()
