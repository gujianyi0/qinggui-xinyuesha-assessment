"""Download checksum-verified Kafka test dependencies into this project's .local only."""
import argparse
import hashlib
import json
import re
import ssl
import tarfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
VERSION = "3.9.1"
ARCHIVE = f"kafka_2.13-{VERSION}.tgz"
URL = f"https://archive.apache.org/dist/kafka/{VERSION}/{ARCHIVE}"


def prepare():
    folder = ROOT / ".local/native-kafka"
    folder.mkdir(parents=True, exist_ok=True)
    archive = folder / ARCHIVE
    with httpx.Client(verify=ssl.create_default_context(), timeout=60, follow_redirects=True) as client:
        checksum = client.get(URL + ".sha512")
        checksum.raise_for_status()
        # Apache's checksum files may wrap the hexadecimal value over lines.
        raw = re.split(r"[:=]", checksum.text, maxsplit=1)[-1]
        digest = "".join(re.findall(r"\b[0-9a-fA-F]{8,}\b", raw)).lower()
        if len(digest) != 128:
            raise ValueError("Unrecognized Apache SHA512 checksum format")
        if not archive.exists():
            partial = archive.with_suffix(".part")
            with client.stream("GET", URL) as response:
                response.raise_for_status()
                with partial.open("wb") as file:
                    for data in response.iter_bytes():
                        file.write(data)
            partial.replace(archive)
    actual = hashlib.sha512(archive.read_bytes()).hexdigest()
    if actual != digest:
        raise ValueError("Kafka archive checksum mismatch; archive was retained for inspection")
    home = folder / f"kafka_2.13-{VERSION}"
    if not (home / "libs").is_dir():
        with tarfile.open(archive) as source:
            for member in source.getmembers():
                destination = (folder / member.name).resolve()
                if not destination.is_relative_to(folder.resolve()) or member.issym() or member.islnk():
                    raise ValueError("Unsafe archive entry")
            source.extractall(folder, filter="data")
    record = {"version": VERSION, "url": URL, "sha512": actual, "home": str(home), "scope": "local temporary verification broker; Compose remains separately required"}
    (folder / "dependency.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return home


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(prepare())
