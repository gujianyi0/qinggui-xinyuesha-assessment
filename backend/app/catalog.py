import asyncio
import hashlib
import json
import math
import re
from pathlib import Path

from sqlalchemy import select, text

from .config import Settings
from .embedding_assets import pinned_model_path
from .models import IndexedChunk, Job, PublishedIndex
from .retrieval_cache import valid_cached_result


def read_json(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else (default if default is not None else [])


def grams(value: str) -> set[str]:
    clean = re.sub(r"[^\w\u4e00-\u9fff]", "", value.lower())
    return {clean[i:i + 2] for i in range(max(0, len(clean) - 1))} | set(re.findall(r"[a-z_]{3,}", value.lower()))


def version_boundary_question(message: str) -> bool:
    return bool(re.search(r'版本|快照|0\.5\.25', message) and re.search(r'一致|保证|服务器|线上|本地修改', message))


def hand_limit_question(message: str) -> bool:
    return bool('弃' in message and '体力' in message and re.search(r'手牌|手上', message) and re.search(r'几|多少', message))


class Catalog:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.reload()

    def reload(self):
        self.entities = read_json(self.settings.data_dir / "catalog.json")
        self.documents = read_json(self.settings.data_dir / "documents.json")
        self.snapshots = read_json(self.settings.data_dir / "snapshots.json")
        skills = {e["attributes"]["internal_id"]: e for e in self.entities if e["kind"] == "skill"}
        for entity in self.entities:
            supporting = []
            if entity["kind"] == "general":
                supporting = [skills[key]["source"] for key in entity["attributes"].get("skills", []) if key in skills]
            elif entity["kind"] == "card":
                prefix = f"{entity['package']}:text:{entity['attributes']['internal_id']}:"
                supporting = [d["source"] for d in self.documents if d["id"].startswith(prefix)]
            entity["description_sources"] = supporting
            entity["attribute_sources"] = []
            if entity["kind"] == "card" and entity["attributes"].get("deck_specs"):
                source = entity["source"]
                path = self.settings.data_dir / "sources" / source["snapshot_id"] / source["path"]
                if path.is_file():
                    lines = path.read_text(encoding="utf-8-sig").splitlines()
                    needle = f'addCardSpec("{entity["attributes"]["internal_id"]}"'
                    matches = [(n, line) for n, line in enumerate(lines, 1) if needle in line]
                    if matches:
                        entity["attribute_sources"] = [{**source, "id": source["id"] + ":deck-spec",
                            "title": entity["name"] + "牌堆配置", "line_start": matches[0][0], "line_end": matches[-1][0],
                            "excerpt": "\n".join(line for _, line in matches)}]

    @property
    def active_id(self) -> str:
        return next((s["id"] for s in self.snapshots if s.get("active")), "")

    def validate_snapshot(self, snapshot_id: str | None) -> str:
        selected = snapshot_id or self.active_id
        if not any(s["id"] == selected for s in self.snapshots):
            raise ValueError("未知资料快照，请先选择已有版本")
        return selected

    def query(self, query: str = "", kind: str | None = None, limit: int = 30) -> list[dict]:
        items = [e for e in self.entities if kind is None or e["kind"] == kind]
        if not query:
            return items[:limit]
        query = query.lower()
        ranked = []
        for entity in items:
            name = entity["name"].lower()
            entity_id = entity["id"].lower()
            score = 100 if name in query or query in name or query in entity_id else 0
            score += len(grams(query) & grams(name + entity.get("description", "")))
            if score:
                ranked.append((score, entity))
        return [entity for _, entity in sorted(ranked, key=lambda pair: pair[0], reverse=True)[:limit]]

    def rulings(self) -> list[dict]:
        data = read_json(self.settings.rulings_dir / "catalog.json")
        return data if isinstance(data, list) else data.get("scenes", data.get("rulings", []))

    def ruling(self, scene_id: str, snapshot_id: str, conditions: dict | None = None, *, reference: bool = False) -> dict:
        scene = next((r for r in self.rulings() if r["id"].upper() == scene_id.upper()), None)
        if scene is None:
            return {"status": "unknown", "message": "该场景尚未收录"}
        if scene.get("snapshot_id") != snapshot_id or scene.get("status") != "verified":
            return {"status": "unverified", "title": scene["title"], "message": "该快照的离线引擎证据尚未验证，不能给出确定裁定", "required_conditions": scene.get("required_conditions", [])}
        if reference:
            return {**scene, "status": "reference", "record_status": "verified",
                    "applicability": "仅查看已执行的固定测试记录，不确认玩家当前局面；必须列明前提和差异"}
        for variant in scene.get("variants", []):
            if all((conditions or {}).get(k) == v for k, v in variant["conditions"].items()):
                return {**scene, **variant, "id": scene["id"], "status": "verified", "snapshot_id": snapshot_id}
        required = dict(scene.get("conditions", {}))
        if scene["id"] == "SC01":
            # blade.lua:20-21 sets these flags itself; they are engine facts, not player input.
            required.pop("bypass_times", None)
            required.pop("bypass_distances", None)
        if required and any((conditions or {}).get(k) != v for k, v in required.items()):
            return {"status": "needs_clarification", "scene_id": scene["id"], "required_conditions": required,
                    "required_context": scene.get("required_conditions", []),
                    "provided_conditions": conditions or {},
                    "verified_variants": [v["conditions"] for v in scene.get("variants", [])],
                    "message": "请把玩家已明确提供的前提映射为上述字段后重试；确实缺少的信息须询问玩家，不能按期望值补齐"}
        return scene


class Embedder:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = None
        self.lock = asyncio.Lock()

    async def encode(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        if self.settings.embedding_mode == "test":
            result = []
            for value in texts:
                vector = [0.0] * 512
                for token in grams(value):
                    index = int.from_bytes(hashlib.sha256(token.encode()).digest()[:4], "big") % 512
                    vector[index] += 1
                norm = math.sqrt(sum(v * v for v in vector)) or 1
                result.append([v / norm for v in vector])
            return result
        if self.settings.embedding_mode != "local":
            raise RuntimeError("向量化未启用")
        if not self.settings.embedding_revision:
            raise RuntimeError("本地向量模型 revision 尚未锁定，请运行 scripts/prepare_embedding.py")
        async with self.lock:
            if self.model is None:
                def load():
                    import torch
                    from sentence_transformers import SentenceTransformer
                    torch.set_num_threads(self.settings.embedding_threads)
                    folder = pinned_model_path(self.settings)
                    if not (folder / "download-manifest.json").is_file():
                        raise RuntimeError("本地向量模型尚未准备，请运行 scripts/prepare_embedding.py --download")
                    return SentenceTransformer(str(folder), device="cpu", local_files_only=True, trust_remote_code=False)
                self.model = await asyncio.to_thread(load)
            inputs = [("为这个句子生成表示以用于检索相关文章：" + t[:400]) if query else t for t in texts]
            if any(len(tokens) > self.model.max_seq_length for tokens in self.model.tokenizer(inputs, truncation=False)["input_ids"]):
                raise ValueError("资料超过向量模型长度限制，请先分块，禁止静默截断")
            vectors = await asyncio.to_thread(self.model.encode, inputs, normalize_embeddings=True, batch_size=16, show_progress_bar=False)
            return vectors.tolist()


class KnowledgeSearch:
    def __init__(self, catalog: Catalog, database, embedder: Embedder, settings: Settings):
        self.catalog, self.database, self.embedder, self.settings = catalog, database, embedder, settings
        from redis.asyncio import Redis
        self.cache = Redis.from_url(settings.redis_url, socket_timeout=0.3, socket_connect_timeout=0.3)

    async def close(self):
        await self.cache.aclose()

    async def search(self, query: str, snapshot_id: str, top_k: int = 5) -> dict:
        top_k = min(max(top_k, 1), 8)
        if version_boundary_question(query):
            # Maintained capability facts are separate from upstream game rules.
            self.catalog.validate_snapshot(snapshot_id)
            path = self.settings.data_dir / 'knowledge-boundaries.md'
            if path.is_file() and snapshot_id == 'freekill-local-b9dc701220bc':
                raw = path.read_bytes()
                document = raw.decode('utf-8')
                source = {'id': 'project-scope:' + snapshot_id, 'title': '当前资料与版本核对范围',
                          'path': 'data/knowledge-boundaries.md', 'snapshot_id': snapshot_id,
                          'evidence_type': 'project_scope', 'line_start': 1, 'line_end': len(document.splitlines()),
                          'excerpt': document, 'sha256': hashlib.sha256(raw).hexdigest()}
                return {'mode': 'maintained_project_scope', 'snapshot_id': snapshot_id,
                        'items': [{'id': source['id'], 'title': source['title'], 'text': document, 'source': source}]}
        async with self.database.sessions() as db:
            published = await db.get(PublishedIndex, snapshot_id)
            index_version = f"{published.job_id}:{published.generation}" if published else "unindexed"
            if published:
                job = await db.get(Job, published.job_id)
                metadata = job.result or {}
                if any(metadata.get(key) != value for key, value in {
                    "embedding_mode": self.settings.embedding_mode,
                    "embedding_model": self.settings.embedding_model,
                    "embedding_revision": self.settings.embedding_revision,
                }.items()):
                    raise ValueError("已发布索引的向量模型配置已变化，请重新导入资料")
        key = "retrieval:" + hashlib.sha256(f"policy-v2:{snapshot_id}:{index_version}:{self.settings.embedding_mode}:{self.settings.embedding_revision}:{query}:{top_k}".encode()).hexdigest()
        expected_mode = "lexical_unindexed" if not published else (
            "pgvector" if self.database.engine.dialect.name == "postgresql" else
            "test_vectors" if self.settings.embedding_mode == "test" else "sqlite_vectors")
        try:
            cached = await self.cache.get(key)
            if cached:
                result = json.loads(cached)
                if valid_cached_result(result, snapshot_id=snapshot_id, top_k=top_k, mode=expected_mode):
                    return result
        except Exception:
            pass
        vector_docs = []
        mode = "lexical_unindexed"
        async with self.database.sessions() as db:
            if published:
                vector = (await self.embedder.encode([query], query=True))[0]
                if db.bind.dialect.name == "postgresql":
                    ids = (await db.execute(text("SELECT v.chunk_id FROM vector_chunks v WHERE v.job_id=:job AND v.generation=:generation ORDER BY v.embedding <=> CAST(:vector AS vector) LIMIT :limit"), {"job": published.job_id, "generation": published.generation, "vector": json.dumps(vector), "limit": top_k})).scalars().all()
                    chunks = list((await db.scalars(select(IndexedChunk).where(IndexedChunk.id.in_(ids)))).all())
                    chunks.sort(key=lambda c: ids.index(c.id))
                    mode = "pgvector"
                else:
                    chunks = list((await db.scalars(select(IndexedChunk).where(IndexedChunk.job_id == published.job_id, IndexedChunk.generation == published.generation))).all())
                    chunks.sort(key=lambda c: sum(a * b for a, b in zip(c.embedding, vector, strict=True)), reverse=True)
                    chunks = chunks[:top_k]
                    mode = "test_vectors" if self.settings.embedding_mode == "test" else "sqlite_vectors"
                vector_docs = [{"id": c.document_id, "text": c.text, "source": c.source, "title": c.source.get("title", c.document_id)} for c in chunks]
        query_grams = grams(query)
        ranked = []
        for document in self.catalog.documents:
            if document.get("source", {}).get("snapshot_id") != snapshot_id:
                continue
            content = document.get("text", "")
            score = len(query_grams & grams(document.get("title", "") + content))
            if document.get("title") and document["title"] in query:
                score += 30
            if score:
                ranked.append((score, document))
        lexical = [document for _, document in sorted(ranked, key=lambda p: p[0], reverse=True)[:top_k]]
        # Preserve one directly matching rule passage rather than letting equipment/skill
        # exceptions crowd the base rule out of a small top-K result.
        rules = [(score, d) for score, d in ranked if d["source"].get("evidence_type") == "rule_text"]
        foundation = [max(rules, key=lambda pair: pair[0])[1]] if rules else []
        seen = set()
        merged = []
        for document in foundation + lexical[:1] + vector_docs + lexical[1:]:
            if document["id"] not in seen:
                seen.add(document["id"])
                passage = document.get("text", "")[:2200]
                source = {**document["source"], "id": f"{document['source']['id']}:passage:{document['id']}", "excerpt": passage[:1000]}
                merged.append({"id": document["id"], "title": document.get("title", ""), "text": passage, "source": source})
        result = {"mode": mode, "snapshot_id": snapshot_id, "items": merged[:top_k]}
        try:
            await self.cache.setex(key, self.settings.cache_ttl_seconds, json.dumps(result, ensure_ascii=False))
        except Exception:
            pass
        return result
