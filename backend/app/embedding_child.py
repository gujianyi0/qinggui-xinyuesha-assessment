"""One-job embedding sidecar. Stdout is a JSON protocol; diagnostics use stderr."""
import asyncio
import contextlib
import json
import os
import sys

from .catalog import Embedder
from .config import Settings


def send(value):
    sys.__stdout__.write(json.dumps(value, ensure_ascii=False) + "\n")
    sys.__stdout__.flush()


async def run():
    send({"pid": os.getpid(), "ready": True})
    config = json.loads(sys.stdin.buffer.readline())
    embedder = Embedder(Settings(_env_file=None, **config))
    while raw := sys.stdin.buffer.readline():
        body = json.loads(raw)
        try:
            vectors = await embedder.encode(body["texts"], query=body.get("query", False))
            send({"vectors": vectors})
        except MemoryError:
            os.write(2, b"embedding_fatal MemoryError\n")
            return 75
        except Exception as error:
            # Texts, environment and credentials are never echoed in diagnostics.
            send({"error": type(error).__name__})
    return 0


if __name__ == "__main__":
    with contextlib.redirect_stdout(sys.stderr):
        raise SystemExit(asyncio.run(run()))
