"""Resolve and record a pinned BGE revision; download only with --download."""
import argparse
import asyncio
import hashlib
import json
import ssl
import time
from datetime import datetime, timezone

import httpx

from backend.app.config import ROOT, Settings
from backend.app.embedding_assets import pinned_model_path


def download_model(client, settings, revision, metadata):
    settings.embedding_revision = revision
    folder = pinned_model_path(settings)
    folder.mkdir(parents=True, exist_ok=True)
    files = []
    for item in metadata["siblings"]:
        name = item["rfilename"]
        if not (name in {"model.safetensors", "vocab.txt", "tokenizer.json", "config.json", "config_sentence_transformers.json", "modules.json", "sentence_bert_config.json", "special_tokens_map.json", "tokenizer_config.json"} or name == "1_Pooling/config.json"):
            continue
        path = (folder / name).resolve()
        if not path.is_relative_to(folder.resolve()):
            raise ValueError("Unsafe model asset path")
        path.parent.mkdir(parents=True, exist_ok=True)

        def verified():
            if not path.is_file() or path.stat().st_size != item["size"]:
                return False
            data = path.read_bytes()
            if item.get("lfs"):
                return hashlib.sha256(data).hexdigest() == item["lfs"]["sha256"]
            return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest() == item["blobId"]

        if not verified():
            url = f"https://huggingface.co/{settings.embedding_model}/resolve/{revision}/{name}"
            for attempt in range(3):
                with client.stream("GET", url) as response:
                    if response.status_code in {500, 502, 503, 504} and attempt < 2:
                        time.sleep(1 + attempt)
                        continue
                    if response.status_code != 200:
                        raise RuntimeError(f"Model asset {name}: HTTP {response.status_code}; download stopped")
                    partial = path.with_suffix(path.suffix + ".part")
                    with partial.open("wb") as target:
                        for chunk in response.iter_bytes():
                            target.write(chunk)
                    partial.replace(path)
                    break
            if not verified():
                raise ValueError(f"Model asset integrity check failed: {name}")
        files.append({"path": name, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        print(f"Verified {name}", flush=True)
    if not any(file["path"] == "model.safetensors" for file in files):
        raise ValueError("Pinned model has no safetensors weights")
    (folder / "download-manifest.json").write_text(json.dumps({"model": settings.embedding_model, "revision": revision, "files": files}, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision")
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    if settings.embedding_model != "BAAI/bge-small-zh-v1.5":
        parser.error("the current database expects the approved 512-dimensional BGE model")
    with httpx.Client(timeout=60, follow_redirects=True, verify=ssl.create_default_context()) as client:
        revision_ref = args.revision or settings.embedding_revision or "main"
        for attempt in range(3):
            response = client.get(f"https://huggingface.co/api/models/{settings.embedding_model}/revision/{revision_ref}?blobs=true")
            if response.status_code not in {500, 502, 503, 504} or attempt == 2:
                break
            time.sleep(1 + attempt)
        response.raise_for_status()
        revision = response.json()["sha"]
        if args.download:
            download_model(client, settings, revision, response.json())
    record = {"model": settings.embedding_model, "revision": revision, "dimension": 512,
              "resolved_at": datetime.now(timezone.utc).isoformat(), "downloaded": False}
    if args.download:
        from backend.app.catalog import Embedder
        settings.embedding_mode, settings.embedding_revision = "local", revision
        vectors = asyncio.run(Embedder(settings).encode(["新月杀规则资料验证"]))
        assert len(vectors[0]) == 512
        record["downloaded"] = True
    path = ROOT / ".local/embedding-lock.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"EMBEDDING_REVISION={revision}")
    print("Pin this revision in this project's .env. No proxy or login settings were changed.")


if __name__ == "__main__":
    main()
