"""Prepare official portable PostgreSQL and pgvector sources inside project .local."""
import hashlib
import json
import ssl
import zipfile

import httpx

from backend.app.config import ROOT


def download(client, url, destination):
    if not destination.is_file():
        with client.stream("GET", url) as response:
            response.raise_for_status()
            partial = destination.with_suffix(".part")
            with partial.open("wb") as file:
                for data in response.iter_bytes():
                    file.write(data)
            partial.replace(destination)
    return {"url": url, "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(), "bytes": destination.stat().st_size}


def extract(archive, parent, prefix=None):
    with zipfile.ZipFile(archive) as source:
        for item in source.infolist():
            if prefix and not any(item.filename.startswith(value) for value in prefix):
                continue
            if not (parent / item.filename).resolve().is_relative_to(parent.resolve()):
                raise ValueError("Unsafe archive path")
            source.extract(item, parent)


def main():
    folder = ROOT / ".local/native-postgres"
    folder.mkdir(parents=True, exist_ok=True)
    records = {}
    with httpx.Client(verify=ssl.create_default_context(), timeout=60, follow_redirects=True) as client:
        postgres = folder / "postgresql-17.11-1-windows-x64-binaries.zip"
        records["postgresql"] = download(client, "https://get.enterprisedb.com/postgresql/" + postgres.name, postgres)
        if not (folder / "pgsql/bin/postgres.exe").is_file():
            extract(postgres, folder, ("pgsql/bin/", "pgsql/lib/", "pgsql/share/", "pgsql/include/", "pgsql/LICENSE"))
        vector = folder / "pgvector-v0.8.7.zip"
        records["pgvector"] = download(client, "https://codeload.github.com/pgvector/pgvector/zip/refs/tags/v0.8.7", vector)
        if not (folder / "pgvector-0.8.7/Makefile.win").is_file():
            extract(vector, folder)
    (folder / "dependency.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    print("Prepared local PostgreSQL 17.11 binaries and pgvector 0.8.7 source; no Windows service installed.")


if __name__ == "__main__":
    main()
