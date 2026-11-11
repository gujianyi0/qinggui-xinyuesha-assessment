"""Resolve the prepared, pinned optional Windows Redis dependency."""
import hashlib
import json
from pathlib import Path

from .config import ROOT

VERSION = "7.4.11"
ARCHIVE = f"Redis-{VERSION}-Windows-x64-cygwin.zip"
SHA256 = "835999942bbef27e2b01f4a36955522cf19fff6511e67bbfe3fee322f6586705"


def prepared_redis(root=ROOT):
    folder = root / ".local/native-redis"
    manifest = folder / "dependency.json"
    if not manifest.is_file():
        return None
    value = json.loads(manifest.read_text(encoding="utf-8"))
    server = Path(value["server"]).resolve()
    if not server.is_relative_to(folder.resolve()) or not server.is_file():
        raise ValueError("Prepared Redis must stay inside the project")
    if value.get("version") != VERSION or value.get("sha256") != SHA256:
        raise ValueError("Prepared Redis release does not match the pinned archive")
    if hashlib.sha256(server.read_bytes()).hexdigest() != value.get("server_sha256"):
        raise ValueError("Prepared Redis executable checksum differs; run prepare_native_redis.py")
    return server
