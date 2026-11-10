"""Prepare a checksum-pinned community Windows Redis build for local tests only."""
import hashlib
import json
import ssl
import time
import zipfile

import httpx
import truststore

from backend.app.config import ROOT

VERSION = "7.4.11"
ARCHIVE = f"Redis-{VERSION}-Windows-x64-cygwin.zip"
SHA256 = "835999942bbef27e2b01f4a36955522cf19fff6511e67bbfe3fee322f6586705"
URL = f"https://github.com/redis-windows/redis-windows/releases/download/{VERSION}/{ARCHIVE}"


def main():
    folder = ROOT / ".local/native-redis"
    folder.mkdir(parents=True, exist_ok=True)
    archive = folder / ARCHIVE
    if not archive.is_file():
        with httpx.Client(verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT), timeout=60, follow_redirects=True) as client:
            for attempt in range(3):
                with client.stream("GET", URL) as response:
                    if response.status_code in {500, 502, 503, 504} and attempt < 2:
                        time.sleep(1 + attempt)
                        continue
                    if response.status_code != 200:
                        raise RuntimeError(f"Redis archive HTTP {response.status_code}; download stopped")
                    partial = archive.with_suffix(".part")
                    with partial.open("wb") as file:
                        for data in response.iter_bytes():
                            file.write(data)
                    partial.replace(archive)
                    break
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != SHA256:
        raise ValueError("Redis archive hash differs from the pinned release asset")
    home = folder / VERSION
    home.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as source:
        for item in source.infolist():
            if not (home / item.filename).resolve().is_relative_to(home.resolve()):
                raise ValueError("Unsafe archive path")
            source.extract(item, home)
    server = next(home.rglob("redis-server.exe"))
    record = {"version": VERSION, "source": URL, "sha256": digest, "server": str(server),
              "provenance": "redis-windows community Cygwin build, not the official Linux container", "windows_service_installed": False}
    (folder / "dependency.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print("Prepared checksum-verified Redis 7.4.11 community Windows build; no service installed.")


if __name__ == "__main__":
    main()
