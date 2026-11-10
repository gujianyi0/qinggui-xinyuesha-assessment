"""Keep torch/model allocations out of the long-lived queue consumer."""
import asyncio
import json
import os
import subprocess
import sys

from .config import ROOT
from .native_process import WindowsJob


class IsolatedEmbedder:
    def __init__(self, settings):
        self.settings, self.process, self.container = settings, None, None
        self.lock = asyncio.Lock()

    async def _read(self):
        line = await asyncio.wait_for(self.process.stdout.readline(), timeout=120)
        if not line:
            code = await self.process.wait()
            if code == 75:
                raise MemoryError("embedding sidecar exhausted memory")
            raise ConnectionError(f"embedding sidecar exited ({code})")
        return json.loads(line)

    async def encode(self, texts: list[str], *, query=False):
        async with self.lock:
            if self.process is None:
                self.container = WindowsJob()
                self.process = await asyncio.create_subprocess_exec(
                    sys.executable, "-u", "-m", "backend.app.embedding_child", cwd=ROOT,
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    limit=2 * 1024 * 1024,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                self.container.assign(self.process.pid)
                hello = await self._read()
                # venv's Windows redirector has a different PID from the actual interpreter.
                self.container.assign(hello["pid"])
                fields = ("embedding_mode", "embedding_model", "embedding_revision", "embedding_threads")
                config = {key: getattr(self.settings, key) for key in fields}
                self.process.stdin.write((json.dumps(config) + "\n").encode())
            self.process.stdin.write((json.dumps({"texts": texts, "query": query}, ensure_ascii=False) + "\n").encode())
            await self.process.stdin.drain()
            result = await self._read()
            if result.get("error") == "ValueError":
                raise ValueError("资料不符合向量化输入限制")
            if result.get("error") or "vectors" not in result:
                raise ConnectionError("embedding sidecar failed")
            return result["vectors"]

    async def close(self):
        process, container = self.process, self.container
        self.process = self.container = None
        try:
            if process is not None and process.returncode is None:
                process.stdin.close()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except TimeoutError:
                    process.kill()
                    await process.wait()
        finally:
            if container is not None:
                container.close()
