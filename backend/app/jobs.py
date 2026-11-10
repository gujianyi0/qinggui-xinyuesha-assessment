import datetime as dt
import json

from sqlalchemy import and_, or_, select, text, update
from sqlalchemy.exc import IntegrityError

from .chunking import CHUNK_OVERLAP, CHUNK_SIZE, chunk_documents
from .models import IndexedChunk, Job, JobAttempt, Outbox, PublishedIndex, now

TERMINAL = {"succeeded", "failed", "cancelled"}


class StaleExecution(Exception):
    pass


class Jobs:
    def __init__(self, settings, database, catalog, embedder):
        self.settings, self.database, self.catalog, self.embedder = settings, database, catalog, embedder

    @staticmethod
    def enqueue(db, job):
        db.add(Outbox(job_id=job.id, payload={"job_id": job.id, "expected_generation": job.generation}))

    async def create(self, user_id: str, snapshot_id: str, key: str) -> Job:
        self.catalog.validate_snapshot(snapshot_id)
        async with self.database.sessions() as db:
            existing = await db.scalar(select(Job).where(Job.user_id == user_id, Job.idempotency_key == key))
            if existing:
                if existing.snapshot_id != snapshot_id:
                    raise ValueError("幂等键已用于其他资料快照")
                return existing
            job = Job(user_id=user_id, snapshot_id=snapshot_id, idempotency_key=key, status="queued", generation=0)
            db.add(job)
            try:
                await db.flush()
                self.enqueue(db, job)
                await db.commit()
                return job
            except IntegrityError:
                await db.rollback()
                existing = await db.scalar(select(Job).where(Job.user_id == user_id, Job.idempotency_key == key))
                if existing is None or existing.snapshot_id != snapshot_id:
                    raise ValueError("幂等键冲突") from None
                return existing

    async def cancel(self, job_id: str):
        async with self.database.sessions.begin() as db:
            await db.execute(update(Job).where(Job.id == job_id, Job.status.in_(["queued", "retry_wait"])).values(status="cancelled", lease_until=None, retry_at=None))
            await db.execute(update(Job).where(Job.id == job_id, Job.status == "running").values(status="cancel_requested"))
            return await db.get(Job, job_id)

    async def claim(self, job_id: str, expected_generation: int) -> Job | None:
        async with self.database.sessions.begin() as db:
            result = await db.execute(update(Job).where(Job.id == job_id, Job.status == "queued", Job.generation == expected_generation, Job.attempts < self.settings.max_job_attempts).values(status="running", generation=Job.generation + 1, attempts=Job.attempts + 1, error=None, lease_until=now() + dt.timedelta(seconds=self.settings.lease_seconds)))
            if result.rowcount != 1:
                return None
            job = await db.get(Job, job_id)
            db.add(JobAttempt(job_id=job.id, generation=job.generation, status="running"))
            return job

    async def heartbeat(self, job_id: str, generation: int):
        async with self.database.sessions.begin() as db:
            result = await db.execute(update(Job).where(Job.id == job_id, Job.generation == generation, Job.status == "running").values(lease_until=now() + dt.timedelta(seconds=self.settings.lease_seconds)))
            if result.rowcount != 1:
                raise StaleExecution

    async def process(self, job: Job, *, fault: str | None = None):
        self.catalog.validate_snapshot(job.snapshot_id)
        documents = [d for d in self.catalog.documents if d.get("source", {}).get("snapshot_id") == job.snapshot_id]
        if not documents:
            raise ValueError("资料快照没有可索引正文")
        document_count = len(documents)
        documents = chunk_documents(documents)
        for offset in range(0, len(documents), 16):
            await self.heartbeat(job.id, job.generation)
            batch = documents[offset:offset + 16]
            vectors = await self.embedder.encode([d["text"] for d in batch])
            async with self.database.sessions.begin() as db:
                current = await db.scalar(select(Job).where(Job.id == job.id).with_for_update())
                if current.generation != job.generation or current.status != "running":
                    raise StaleExecution
                for document, vector in zip(batch, vectors, strict=True):
                    chunk = IndexedChunk(job_id=job.id, generation=job.generation, document_id=document["id"], text=document["text"], source=document["source"], embedding=vector)
                    db.add(chunk)
                    await db.flush()
                    if db.bind.dialect.name == "postgresql":
                        await db.execute(text("INSERT INTO vector_chunks(chunk_id,job_id,generation,embedding) VALUES (:id,:job,:generation,CAST(:vector AS vector))"), {"id": chunk.id, "job": job.id, "generation": job.generation, "vector": json.dumps(vector)})
                current.progress = min(99, int((offset + len(batch)) * 100 / len(documents)))
            if fault == "temporary":
                raise ConnectionError("Injected temporary dependency failure")
        async with self.database.sessions.begin() as db:
            result = await db.execute(update(Job).where(Job.id == job.id, Job.generation == job.generation, Job.status == "running").values(status="succeeded", progress=100, lease_until=None, result={"snapshot_id": job.snapshot_id, "documents": document_count, "chunks": len(documents), "chunk_size": CHUNK_SIZE, "chunk_overlap": CHUNK_OVERLAP, "embedding_mode": self.settings.embedding_mode, "embedding_model": self.settings.embedding_model, "embedding_revision": self.settings.embedding_revision}))
            if result.rowcount != 1:
                raise StaleExecution
            if db.bind.dialect.name == "postgresql":
                await db.execute(text("INSERT INTO published_indexes(snapshot_id,job_id,generation,published_at) VALUES (:snapshot,:job,:generation,:published) ON CONFLICT(snapshot_id) DO UPDATE SET job_id=EXCLUDED.job_id,generation=EXCLUDED.generation,published_at=EXCLUDED.published_at"), {"snapshot": job.snapshot_id, "job": job.id, "generation": job.generation, "published": now()})
            else:
                index = await db.get(PublishedIndex, job.snapshot_id)
                if index:
                    index.job_id, index.generation, index.published_at = job.id, job.generation, now()
                else:
                    db.add(PublishedIndex(snapshot_id=job.snapshot_id, job_id=job.id, generation=job.generation))
            await db.execute(update(JobAttempt).where(JobAttempt.job_id == job.id, JobAttempt.generation == job.generation).values(status="succeeded"))

    async def fail(self, job_id: str, generation: int, error: Exception):
        async with self.database.sessions.begin() as db:
            job = await db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if job.generation != generation or job.status in TERMINAL:
                return
            reason = f"{type(error).__name__}: " + (str(error)[:200] if isinstance(error, ValueError) else "后台依赖暂时不可用")
            if job.status == "cancel_requested":
                job.status, job.error = "cancelled", "用户取消，暂存索引未发布"
            elif isinstance(error, ValueError) or job.attempts >= self.settings.max_job_attempts:
                job.status, job.error = "failed", reason
            else:
                job.status, job.error = "retry_wait", reason
                job.retry_at = now() + dt.timedelta(seconds=self.settings.retry_delays[min(job.attempts - 1, 1)])
            job.lease_until = None
            await db.execute(update(JobAttempt).where(JobAttempt.job_id == job_id, JobAttempt.generation == generation).values(status=job.status, error=job.error))

    async def recover(self):
        async with self.database.sessions.begin() as db:
            # Row locks + status/generation predicates fence concurrent recovery loops.
            due_at = now()
            due = list((await db.scalars(select(Job).where(or_(
                and_(Job.status.in_(["running", "cancel_requested"]), Job.lease_until < due_at),
                and_(Job.status == "retry_wait", Job.retry_at <= due_at),
            )).order_by(Job.created_at).limit(100).with_for_update(skip_locked=True))).all())
            for job in due:
                expired = job.status in ("running", "cancel_requested") and job.lease_until and job.lease_until < now()
                retry = job.status == "retry_wait" and job.retry_at and job.retry_at <= now()
                if not (expired or retry):
                    continue
                if job.status == "cancel_requested":
                    job.status, job.error = "cancelled", "取消已生效"
                elif job.attempts >= self.settings.max_job_attempts:
                    job.status, job.error = "failed", "执行中断且已达到最大尝试次数"
                else:
                    await db.execute(update(JobAttempt).where(JobAttempt.job_id == job.id, JobAttempt.generation == job.generation, JobAttempt.status == "running").values(status="interrupted", error="执行租约过期"))
                    job.generation += 1  # Fence the original worker before scheduling its replacement.
                    job.status, job.lease_until, job.retry_at = "queued", None, None
                    self.enqueue(db, job)
                if job.status in TERMINAL:
                    job.lease_until, job.retry_at = None, None
                    await db.execute(update(JobAttempt).where(JobAttempt.job_id == job.id, JobAttempt.generation == job.generation, JobAttempt.status == "running").values(status=job.status, error=job.error))
