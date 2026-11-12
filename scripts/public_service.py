"""Supervise the local gateway and a short HTTPS pull relay over port 443."""
import asyncio
import contextlib
import datetime as dt
import json
import os
import socket
import subprocess
import sys
import time

import httpx

from backend.app.config import ROOT

LOCAL = ROOT / ".local/public-entry"


def write_status(value):
    value.update(updated_at=dt.datetime.now(dt.UTC).isoformat(), pid=os.getpid())
    temporary = LOCAL / "status.tmp"
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(LOCAL / "status.json")


async def handle_request(message, client, config):
    if not isinstance(message, dict) or not isinstance(message.get("id"), str):
        raise ValueError("Invalid relay envelope")
    path = message.get("path", "")
    if not isinstance(path, str) or not path.startswith("/api/") or "#" in path or message.get("method") not in ("GET", "POST", "PATCH"):
        return {"id": message["id"], "status": 400, "body": '{"detail":"Invalid relay request"}'}
    body = message.get("body", "")
    if not isinstance(body, str) or len(body.encode()) > 48000:
        return {"id": message["id"], "status": 413, "body": '{"detail":"Request too large"}'}
    try:
        result = await client.request(message["method"], "http://127.0.0.1:18083" + path, content=body.encode(),
                                      headers={"X-Public-Edge": config["edge_token"], "Content-Type": "application/json",
                                               "Authorization": message.get("authorization", "")})
        if len(result.content) > 3000000:
            return {"id": message["id"], "status": 503, "body": '{"detail":"Response too large"}'}
        return {"id": message["id"], "status": result.status_code, "body": result.text}
    except httpx.HTTPError:
        return {"id": message["id"], "status": 503, "body": '{"detail":"Local service unavailable"}'}


async def run():
    LOCAL.mkdir(parents=True, exist_ok=True)
    config = json.loads((LOCAL / "config.json").read_text(encoding="utf-8"))
    guard = socket.socket()
    if os.name == "nt":
        guard.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        guard.bind(("127.0.0.1", 18084))
        guard.listen(1)
    except OSError:
        raise SystemExit("Public entry supervisor already running") from None
    gateway = None
    log = (LOCAL / "gateway.log").open("ab")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    state = {"state": "starting", "public_url": config["public_url"], "reconnects": 0, "transport": "https-pull-443"}
    delay = 1
    remote_headers = {"Authorization": "Bearer " + config["control_token"]}
    limits = httpx.Limits(max_connections=40, max_keepalive_connections=0)
    async with httpx.AsyncClient(trust_env=False, timeout=40) as client, httpx.AsyncClient(timeout=20, limits=limits) as remote:
        pending = set()
        try:
            while not (LOCAL / "stop").exists():
                if gateway is None or gateway.poll() is not None:
                    gateway = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.public_gateway:application",
                                                "--factory", "--host", "127.0.0.1", "--port", "18083", "--no-access-log"],
                                               cwd=ROOT, stdout=log, stderr=log, creationflags=flags)
                    state["gateway_pid"] = gateway.pid
                try:
                    response = await remote.get(config["public_url"] + "/__poll", headers=remote_headers)
                    response.raise_for_status()
                    batch = response.json()
                    if batch.get("reconnect"):
                        raise ConnectionError("Owner reconnect check")
                    if state["state"] != "online":
                        state.update(state="online")
                        state.pop("error", None)
                    write_status(state)
                    delay = 1

                    async def respond(message):
                        started = time.monotonic()
                        with (LOCAL / "relay-events.jsonl").open("a", encoding="utf-8") as events:
                            events.write(json.dumps({"id": message.get("id"), "path": message.get("path"), "stage": "received", "time": dt.datetime.now(dt.UTC).isoformat()}) + "\n")
                        result = await handle_request(message, client, config)
                        for attempt in range(3):
                            try:
                                posted = await remote.post(config["public_url"] + "/__reply", headers=remote_headers, json=result)
                                posted.raise_for_status()
                                break
                            except httpx.HTTPError:
                                if attempt == 2:
                                    raise
                                await asyncio.sleep(.5)
                        with (LOCAL / "relay-events.jsonl").open("a", encoding="utf-8") as events:
                            events.write(json.dumps({"id": result["id"], "status": result["status"], "stage": "replied", "elapsed_ms": round((time.monotonic() - started) * 1000)}) + "\n")

                    for message in batch.get("messages", []):
                        task = asyncio.create_task(respond(message))
                        pending.add(task)
                        task.add_done_callback(pending.discard)
                        task.add_done_callback(lambda result: result.exception() if not result.cancelled() else None)
                except Exception as exc:
                    state.update(state="reconnecting", error=type(exc).__name__, reconnects=state["reconnects"] + 1)
                    diagnostic = str(exc)
                    for key in ("edge_token", "control_token", "service_token", "signing_key"):
                        diagnostic = diagnostic.replace(config[key], "[redacted]")
                    with (LOCAL / "relay-events.jsonl").open("a", encoding="utf-8") as events:
                        events.write(json.dumps({"stage": "disconnected", "type": type(exc).__name__, "detail": diagnostic, "time": dt.datetime.now(dt.UTC).isoformat()}) + "\n")
                    write_status(state)
                    for _ in range(delay):
                        if (LOCAL / "stop").exists():
                            break
                        await asyncio.sleep(1)
                    delay = min(delay * 2, 15)
        finally:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            with contextlib.suppress(httpx.HTTPError):
                await remote.post(config["public_url"] + "/__disconnect", headers=remote_headers)
            if gateway is not None and gateway.poll() is None:
                gateway.terminate()
                with contextlib.suppress(subprocess.TimeoutExpired):
                    gateway.wait(timeout=10)
                if gateway.poll() is None:
                    gateway.kill()
                    gateway.wait()
            write_status({**state, "state": "stopped"})
            log.close()
            guard.close()


if __name__ == "__main__":
    asyncio.run(run())
