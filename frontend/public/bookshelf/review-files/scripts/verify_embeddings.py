"""Run actual pinned CPU BGE indexing and retrieval on an isolated SQLite database."""
import argparse
import asyncio
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from backend.app.catalog import Catalog, Embedder, KnowledgeSearch
from backend.app.config import Settings
from backend.app.db import Database
from backend.app.embedding_assets import pinned_model_path
from backend.app.jobs import Jobs
from backend.app.models import IndexedChunk, Job, User

ROOT = Path(__file__).resolve().parents[1]


async def verify(args):
    if not args.label or Path(args.label).name != args.label or args.label in {".", ".."}:
        raise ValueError("label must be a single directory name")
    local = ROOT / ".local/infra" / args.label
    evidence = ROOT / "docs/evidence" / args.label
    local.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    url = f"sqlite+aiosqlite:///{(local / 'bge.sqlite3').as_posix()}"
    env = {**os.environ, "DATABASE_URL": url}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env, check=True, capture_output=True)
    settings = Settings(_env_file=None, database_url=url, embedding_mode="local", redis_url="redis://127.0.0.1:1/0")
    database = Database(settings)
    await database.initialize(settings)
    catalog, embedder = Catalog(settings), Embedder(settings)
    jobs = Jobs(settings, database, catalog, embedder)
    search = KnowledgeSearch(catalog, database, embedder, settings)
    record = {"started_at": datetime.now(timezone.utc).isoformat(), "model": settings.embedding_model,
              "revision": settings.embedding_revision, "device": "cpu", "threads": settings.embedding_threads,
              "scope": "Actual BGE CPU inference, persistent indexing and cosine retrieval on SQLite; pgvector/PostgreSQL and real chat model remain separately unverified"}
    try:
        async with database.sessions() as db:
            user = await db.scalar(select(User).where(User.username == "alice"))
        job = await jobs.create(user.id, catalog.active_id, args.label)
        claimed = await jobs.claim(job.id, 0)
        started = time.perf_counter()
        await jobs.process(claimed)
        record["index_elapsed_seconds"] = round(time.perf_counter() - started, 3)
        async with database.sessions() as db:
            stored = await db.get(Job, job.id)
            chunks = list(await db.scalars(select(IndexedChunk).where(IndexedChunk.job_id == job.id)))
            assert stored.status == "succeeded"
            assert all(len(chunk.embedding) == 512 for chunk in chunks)
            assert all(abs(math.sqrt(sum(x*x for x in chunk.embedding)) - 1) < 0.001 for chunk in chunks)
        record["job_id"], record["index"] = job.id, stored.result
        queries = [
            ("手里一张牌也没有时不能成为杀和决斗的目标", "空城"),
            ("把红色牌当作杀来使用", "武圣"),
            ("受到伤害后获得造成伤害的那张牌", "奸雄"),
            ("卸下这件防具以后恢复一点体力", "白银狮子"),
            ("一个回合里能多次使用杀的武器", "诸葛连弩"),
        ]
        rows = []
        for query, expected in queries:
            started = time.perf_counter()
            vector = (await embedder.encode([query], query=True))[0]
            ranked = sorted(chunks, key=lambda chunk: sum(a*b for a,b in zip(chunk.embedding, vector, strict=True)), reverse=True)[:5]
            semantic_hits = [{"id": chunk.document_id, "title": chunk.source.get("title", ""),
                              "score": round(sum(a*b for a,b in zip(chunk.embedding, vector, strict=True)), 5),
                              "text": chunk.text, "source": chunk.source} for chunk in ranked]
            merged = await search.search(query, catalog.active_id)
            assert merged["mode"] == "sqlite_vectors"
            hit = any(expected in item["title"] or expected in item["text"] for item in semantic_hits)
            rows.append({"query": query, "expected_concept": expected, "semantic_top5_contains_concept": hit,
                         "elapsed_seconds": round(time.perf_counter() - started, 3),
                         "semantic_top5": semantic_hits, "hybrid_result": merged})
            print(f"BGE query: {expected}, top5 concept present={hit}", flush=True)
        record.update(vector_dimension=512, indexed_chunks=len(chunks), normalized=True,
                      semantic_probe_count=len(rows), semantic_probe_hits=sum(row["semantic_top5_contains_concept"] for row in rows),
                      results=rows, passed=True,
                      notice="Term presence is only a retrieval probe, not a semantic answer score or live-chat evaluation")
        manifest = json.loads((pinned_model_path(settings) / "download-manifest.json").read_text(encoding="utf-8"))
        (evidence / "model-files.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception as error:
        record.update(passed=False, error_type=type(error).__name__, error=str(error))
        raise
    finally:
        record["finished_at"] = datetime.now(timezone.utc).isoformat()
        (evidence / "summary.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        await search.close()
        await database.close()
    print(json.dumps({key: record[key] for key in ["passed", "indexed_chunks", "index_elapsed_seconds", "semantic_probe_hits", "semantic_probe_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    asyncio.run(verify(parser.parse_args()))
