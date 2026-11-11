"""Freeze the project's native writers and create a checked, private PG archive."""
import argparse
import asyncio
import ctypes
import hashlib
import json
import os
import re
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import asyncpg

from backend.app.config import ROOT
from backend.app.database_transfer import assert_quiescent, assert_same_database, fingerprint
from backend.app.deployment import read_deployment, write_deployment


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


async def backup(label):
    if os.name != "nt" or not re.fullmatch(r"[a-z0-9-]{1,70}", label):
        raise ValueError("Windows native backup requires a unique lowercase ASCII label")
    existing = read_deployment()
    if existing and (existing.get("primary"), existing.get("phase")) != ("native", "active"):
        raise ValueError("已有主库切换标记，禁止从旧库再次导出")
    native = ROOT / ".local/native-demo"
    state = json.loads((native / "status.json").read_text(encoding="utf-8-sig"))
    if state.get("owner") != "qinggui-assessment-native-demo" or state.get("project") != str(ROOT):
        raise ValueError("Unknown native source; preserved")
    connection = await asyncpg.connect(host="127.0.0.1", port=15433, user="assessment", database="assessment", timeout=5)
    try:
        data = await connection.fetchval("SHOW data_directory")
        if not os.path.samefile(data, native / "pgdata"):
            raise ValueError("Source database path does not belong to this project")
        assert_quiescent(await fingerprint(connection))
    finally:
        await connection.close()
    private = ROOT / ".local/migrations" / label
    evidence = ROOT / "docs/evidence" / (label + "-source")
    private.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "label": label,
              "scope": "Own native database only; API/Worker stopped, read-only standalone PG, archive private and excluded from Git"}
    process, handle, drive, pg, cluster = None, None, None, None, None
    success = False
    try:
        write_deployment({"primary": "frozen", "phase": "freezing", "label": label})
        stopped = subprocess.run(["pwsh", "-NoProfile", "-File", str(ROOT / "scripts/stop_native.ps1")], cwd=ROOT, capture_output=True, timeout=20)
        if stopped.returncode:
            raise RuntimeError("Native stop request failed")
        deadline = time.monotonic() + 70
        while True:
            listening = []
            for port in (15174, 18081, 15433, 19094, 16379):
                with socket.socket() as probe:
                    probe.settimeout(0.2)
                    if probe.connect_ex(("127.0.0.1", port)) == 0:
                        listening.append(port)
            if not listening:
                break
            if time.monotonic() > deadline:
                raise TimeoutError("Native services did not stop; no dump taken")
            await asyncio.sleep(0.5)
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        drive = next((f"{letter}:" for letter in "RQPONMLKJIHG" if not mask & (1 << (ord(letter)-ord('A')))), None)
        if not drive:
            raise RuntimeError("No free ASCII DOS alias")
        subprocess.run(["subst", drive, str(ROOT / ".local")], capture_output=True, check=True)
        assert os.path.samefile(drive + "\\", ROOT / ".local")
        alias = Path(drive + "\\")
        pg, cluster = alias / "native-postgres/pgsql", alias / "native-demo/pgdata"
        handle = (private / "readonly-postgres.log").open("wb")
        process = subprocess.Popen([str(pg / "bin/postgres.exe"), "-D", str(cluster), "-h", "127.0.0.1", "-p", "15433",
                                    "-c", "default_transaction_read_only=on", "-c", "shared_buffers=32MB", "-c", "max_connections=10"],
                                   stdout=handle, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 40
        while True:
            try:
                connection = await asyncpg.connect(host="127.0.0.1", port=15433, user="assessment", database="assessment", timeout=2)
                break
            except (OSError, asyncpg.PostgresError):
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Read-only source PostgreSQL did not start") from None
                await asyncio.sleep(0.25)
        try:
            assert await connection.fetchval("SHOW default_transaction_read_only") == "on"
            source = await fingerprint(connection)
            assert_quiescent(source)
            probes = [dict(r) for r in await connection.fetch("SELECT s.id,s.user_id,count(m.id) AS messages FROM sessions s JOIN messages m ON m.session_id=s.id GROUP BY s.id ORDER BY s.created_at DESC LIMIT 3")]
            old_run = await connection.fetchrow("SELECT id,session_id FROM runs WHERE status='completed' AND model_mode='live' ORDER BY created_at DESC LIMIT 1")
            write_json(private / "http-probes.json", {"sessions": probes, "run": dict(old_run) if old_run else None})
            dump_path = alias / "migrations" / label / "source.dump"
            result = await asyncio.to_thread(subprocess.run, [str(pg / "bin/pg_dump.exe"), "-h", "127.0.0.1", "-p", "15433", "-U", "assessment", "-d", "assessment",
                                                             "-Fc", "--no-owner", "--no-privileges", "--file", str(dump_path)], capture_output=True, timeout=180)
            (private / "pg-dump.log").write_bytes(result.stdout + result.stderr)
            if result.returncode:
                raise RuntimeError("pg_dump failed; private source/archive preserved")
            assert_same_database(source, await fingerprint(connection))
        finally:
            await connection.close()
        archive = private / "source.dump"
        with archive.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        write_json(private / "fingerprint.json", source)
        report.update(passed=True, source=source, source_read_only=True, archive_bytes=archive.stat().st_size, archive_sha256=digest)
        write_deployment({"primary": "frozen", "phase": "source_frozen", "label": label,
                          "archive_sha256": digest, "source_spent_cny": source["budget"]["spent"]})
        success = True
    except Exception as error:
        report.update(passed=False, error_type=type(error).__name__, error=str(error))
        raise
    finally:
        if process is not None and process.poll() is None:
            subprocess.run([str(pg / "bin/pg_ctl.exe"), "-D", str(cluster), "-m", "fast", "-w", "stop"], capture_output=True, timeout=30, check=True)
            process.wait(timeout=10)
        if handle:
            handle.close()
        if drive and os.path.samefile(drive + "\\", ROOT / ".local"):
            subprocess.run(["subst", drive, "/D"], check=True, capture_output=True)
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(evidence / "summary.json", report)
        if not success:
            write_deployment({"primary": "native", "phase": "active", "backup_failed": label})
            subprocess.run(["pwsh", "-NoProfile", "-File", str(ROOT / "scripts/start_native.ps1")], cwd=ROOT, capture_output=True, timeout=20)
    print(json.dumps({"passed": True, "archive_sha256": digest, "tables": len(source["tables"]), "budget": source["budget"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    asyncio.run(backup(parser.parse_args().label))
