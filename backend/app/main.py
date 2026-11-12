import asyncio
import datetime as dt
import hashlib
import json
import re
import secrets
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .catalog import Catalog, Embedder, KnowledgeSearch
from .config import Settings
from .db import Database
from .jobs import Jobs
from .models import (
    BudgetAccount,
    ChatSession,
    Draft,
    Feedback,
    Job,
    JobAttempt,
    Message,
    PublishedIndex,
    QQEvent,
    Run,
    Token,
    ToolCall,
    UsageRecord,
    User,
    now,
)
from .public_schemas import PublicIdentity, PublicRunInput
from .runtime import Runtime
from .schemas import (
    ConfirmInput,
    DeliveryInput,
    DraftInput,
    DraftPatch,
    JobInput,
    Login,
    QQInput,
    RunInput,
    SessionInput,
)
from .security import password_hash, password_matches, token_digest


def fields(row) -> dict:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def draft_payload(draft: Draft) -> dict:
    result = fields(draft)
    required = ["actual", "expected", "steps", "context"]
    if draft.category == "client":
        required += ["platform", "client_version"]
    result["missing_fields"] = [key for key in required if not getattr(draft, key)]
    return result


def create_app(settings: Settings | None = None):
    config = settings or Settings()
    database = Database(config)
    catalog = Catalog(config)
    embedder = Embedder(config)
    search = KnowledgeSearch(catalog, database, embedder, config)
    runtime = Runtime(config, database, catalog, search)
    jobs = Jobs(config, database, catalog, embedder)

    @asynccontextmanager
    async def lifespan(app):
        await database.initialize(config)
        await runtime.recover_interrupted()
        yield
        await runtime.close()
        await search.close()
        await database.close()

    app = FastAPI(title="轻归 · 新月杀资料与反馈助手", version="0.1.0", lifespan=lifespan)
    app.state.settings, app.state.database, app.state.runtime = config, database, runtime
    app.state.catalog, app.state.jobs, app.state.search = catalog, jobs, search
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["GET", "POST", "PATCH"], allow_headers=["Authorization", "Content-Type", "X-Assessment-Fault"])

    @app.exception_handler(SQLAlchemyError)
    async def database_error(_, error):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"detail": "数据库暂时不可用，请稍后重试", "retryable": True})

    async def current_user(authorization: str = Header(default="")) -> str:
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "请先登录")
        async with database.sessions() as db:
            token = await db.get(Token, token_digest(authorization[7:]))
            if token is None or token.expires_at <= now():
                raise HTTPException(401, "登录已失效，请重新登录")
            return token.user_id

    async def bridge_auth(x_bridge_token: str = Header(default="")):
        if not config.bridge_token or not secrets.compare_digest(x_bridge_token, config.bridge_token):
            raise HTTPException(401, "桥接服务身份无效")

    async def public_service_auth(x_public_service: str = Header(default="")):
        if not config.public_service_token or not secrets.compare_digest(x_public_service, config.public_service_token):
            raise HTTPException(401, "公共网关身份无效")

    async def owned(model, identifier: str, user_id: str):
        async with database.sessions() as db:
            value = await db.get(model, identifier)
            if value is None or value.user_id != user_id:
                raise HTTPException(404, "记录不存在")
            return value

    async def create_run(session_id: str, user_id: str, body: RunInput, fault: str | None = None):
        await owned(ChatSession, session_id, user_id)
        try:
            snapshot_id = catalog.validate_snapshot(body.snapshot_id)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        async with database.sessions.begin() as db:
            # Lock the parent to serialize creation of active runs on PostgreSQL.
            await db.scalar(select(ChatSession).where(ChatSession.id == session_id).with_for_update())
            active = await db.scalar(select(Run.id).where(Run.session_id == session_id, Run.status == "running"))
            if active:
                raise HTTPException(409, "此会话正在回答，请等待或先取消")
            run = Run(session_id=session_id, user_id=user_id, model_mode=config.model_mode, model_id=config.model_id if config.model_mode == "live" else "deterministic-test-double", snapshot_id=snapshot_id, fault=fault)
            db.add(run)
            db.add(Message(session_id=session_id, role="user", content=body.message))
            await db.flush()
        return run

    async def new_draft(user_id: str, body: DraftInput):
        if body.session_id:
            await owned(ChatSession, body.session_id, user_id)
        async with database.sessions.begin() as db:
            draft = Draft(user_id=user_id, short_code=secrets.token_hex(4).upper(), **body.model_dump())
            db.add(draft)
            await db.flush()
            return draft_payload(draft)

    async def confirm_draft(identifier: str, user_id: str, revision: int):
        async with database.sessions() as db:
            try:
                draft = await db.scalar(select(Draft).where(Draft.id == identifier, Draft.user_id == user_id).with_for_update())
                if draft is None:
                    raise HTTPException(404, "草稿不存在")
                if draft.revision != revision:
                    raise HTTPException(409, "草稿已更新，请查看最新修订后确认")
                existing = await db.scalar(select(Feedback).where(Feedback.draft_id == identifier))
                if existing:
                    return fields(existing) | {"duplicate": True}
                if not draft.actual:
                    raise HTTPException(422, "请先填写实际现象")
                feedback = Feedback(draft_id=draft.id, user_id=user_id, revision=revision, payload=jsonable_encoder(draft_payload(draft)))
                db.add(feedback)
                draft.status = "confirmed"
                await db.commit()
                return fields(feedback) | {"duplicate": False}
            except IntegrityError:
                await db.rollback()
                existing = await db.scalar(select(Feedback).where(Feedback.draft_id == identifier, Feedback.user_id == user_id))
                if existing and existing.revision == revision:
                    return fields(existing) | {"duplicate": True}
                raise HTTPException(409, "草稿发生并发修改，请重新读取") from None

    @app.get("/health")
    async def health():
        async with database.sessions() as db:
            await db.execute(text("SELECT 1"))
            budget = await db.get(BudgetAccount, 1)
            published = await db.get(PublishedIndex, catalog.active_id) if catalog.active_id else None
        try:
            cache_status = "available" if await search.cache.ping() else "unavailable_fallback"
        except Exception:
            cache_status = "unavailable_fallback"
        return {"status": "ok", "cache": cache_status, "model_mode": config.model_mode, "model_id": config.model_id, "snapshot_id": catalog.active_id, "embedding_mode": config.embedding_mode, "index_published": published is not None, "database": database.engine.dialect.name, "fault_injection_enabled": config.enable_test_faults, "budget": {"spent_cny": budget.spent, "reserved_cny": budget.reserved, "limit_cny": config.total_budget_cny, "warning": budget.spent + budget.reserved >= config.budget_warning_cny}}

    @app.post("/auth/token")
    async def login(body: Login):
        async with database.sessions.begin() as db:
            user = await db.scalar(select(User).where(User.username == body.username))
            if user is None or not password_matches(body.password, user.password_hash):
                raise HTTPException(401, "账号或密码不正确")
            raw = secrets.token_urlsafe(32)
            db.add(Token(digest=token_digest(raw), user_id=user.id, expires_at=now() + dt.timedelta(hours=12)))
            return {"access_token": raw, "token_type": "bearer", "user": {"id": user.id, "username": user.username}}

    @app.post("/internal/public/identity", dependencies=[Depends(public_service_auth)])
    async def public_identity(body: PublicIdentity):
        digest = hashlib.sha256(body.client_secret.encode()).hexdigest()
        identifier = "public:" + digest
        # A fixed ID plus conflict recovery handles two simultaneous logins.
        try:
            async with database.sessions.begin() as db:
                if await db.get(User, identifier) is None:
                    db.add(User(id=identifier, username=identifier, password_hash=password_hash(secrets.token_urlsafe(48))))
        except IntegrityError:
            pass
        raw = secrets.token_urlsafe(32)
        async with database.sessions.begin() as db:
            db.add(Token(digest=token_digest(raw), user_id=identifier, expires_at=now() + dt.timedelta(hours=12)))
        return {"access_token": raw, "token_type": "bearer", "user": {"id": identifier, "username": "访客 " + digest[:8]}}

    @app.post("/internal/public/sessions/{identifier}/runs", status_code=202, dependencies=[Depends(public_service_auth)])
    async def public_run(identifier: str, body: PublicRunInput, user_id: str = Depends(current_user)):
        if not user_id.startswith("public:"):
            raise HTTPException(403, "公共入口需要访客身份")
        await owned(ChatSession, identifier, user_id)
        try:
            snapshot_id = catalog.validate_snapshot(body.snapshot_id)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, user_id + ":" + str(body.request_id)))
        async with database.sessions.begin() as db:
            # The existing ledger serializes public request deduplication and admission.
            # reserve_budget still owns the monetary reservation before any paid call.
            await db.scalar(select(BudgetAccount).where(BudgetAccount.id == 1).with_for_update())
            existing = await db.get(Run, run_id)
            if existing:
                if existing.session_id != identifier:
                    raise HTTPException(409, "请求编号已用于其他会话")
                return {"run_id": run_id, "duplicate": True}
            await db.scalar(select(ChatSession).where(ChatSession.id == identifier).with_for_update())
            if await db.scalar(select(Run.id).where(Run.session_id == identifier, Run.status == "running")):
                raise HTTPException(409, "此会话正在回答，请等待或先取消")
            run = Run(id=run_id, session_id=identifier, user_id=user_id, model_mode=config.model_mode,
                      model_id=config.model_id if config.model_mode == "live" else "deterministic-test-double", snapshot_id=snapshot_id)
            db.add(run)
            db.add(Message(session_id=identifier, role="user", content=body.message))
        runtime.start(run_id, body.message, discard_events=True)
        return {"run_id": run_id, "duplicate": False}

    @app.get("/sessions")
    async def list_sessions(user_id: str = Depends(current_user)):
        async with database.sessions() as db:
            return [fields(s) for s in await db.scalars(select(ChatSession).where(ChatSession.user_id == user_id).order_by(ChatSession.created_at.desc()))]

    @app.post("/sessions", status_code=201)
    async def add_session(body: SessionInput, user_id: str = Depends(current_user)):
        async with database.sessions.begin() as db:
            session = ChatSession(user_id=user_id, title=body.title)
            db.add(session)
            await db.flush()
            return fields(session)

    @app.get("/sessions/{identifier}/messages")
    async def messages(identifier: str, user_id: str = Depends(current_user)):
        await owned(ChatSession, identifier, user_id)
        async with database.sessions() as db:
            return [fields(m) for m in await db.scalars(select(Message).where(Message.session_id == identifier).order_by(Message.created_at))]

    @app.post("/sessions/{identifier}/runs")
    async def run_chat(identifier: str, body: RunInput, request: Request, x_assessment_fault: str | None = Header(default=None), user_id: str = Depends(current_user)):
        if x_assessment_fault and (not config.enable_test_faults or x_assessment_fault != "tool_unavailable"):
            raise HTTPException(400, "故障注入未启用或故障类型无效")
        run = await create_run(identifier, user_id, body, x_assessment_fault)
        queue = runtime.start(run.id, body.message)

        async def events():
            try:
                while True:
                    try:
                        item = await asyncio.wait_for(queue.get(), timeout=1)
                    except TimeoutError:
                        if await request.is_disconnected():
                            await runtime.cancel(run.id)
                            break
                        yield ": keep-alive\n\n"
                        continue
                    if item is None:
                        break
                    event, payload = item
                    yield f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            finally:
                if run.id in runtime.cancellations:
                    await runtime.cancel(run.id)
        return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/runs/{identifier}")
    async def get_run(identifier: str, user_id: str = Depends(current_user)):
        run = await owned(Run, identifier, user_id)
        async with database.sessions() as db:
            calls = list(await db.scalars(select(ToolCall).where(ToolCall.run_id == identifier).order_by(ToolCall.created_at)))
            usage = await db.get(UsageRecord, identifier)
        return fields(run) | {"tool_calls": [fields(c) for c in calls], "usage": fields(usage) if usage else {"input_tokens": run.input_tokens, "output_tokens": run.output_tokens, "estimated": True, "charged_cny": 0}}

    @app.post("/runs/{identifier}/cancel")
    async def cancel_run(identifier: str, user_id: str = Depends(current_user)):
        await owned(Run, identifier, user_id)
        await runtime.cancel(identifier)
        return fields(await owned(Run, identifier, user_id))

    @app.get("/catalog/snapshots")
    async def snapshots(user_id: str = Depends(current_user)):
        return catalog.snapshots

    @app.get("/catalog/entities")
    async def entities(query: str = Query(default="", max_length=500), kind: str | None = Query(default=None, pattern="^(general|card|skill)$"), user_id: str = Depends(current_user)):
        return catalog.query(query, kind, 200)

    @app.get("/catalog/rulings")
    async def rulings(user_id: str = Depends(current_user)):
        return catalog.rulings()

    @app.get("/feedback-drafts")
    async def drafts(user_id: str = Depends(current_user)):
        async with database.sessions() as db:
            return [draft_payload(d) for d in await db.scalars(select(Draft).where(Draft.user_id == user_id).order_by(Draft.created_at.desc()))]

    @app.post("/feedback-drafts", status_code=201)
    async def add_draft(body: DraftInput, user_id: str = Depends(current_user)):
        return await new_draft(user_id, body)

    @app.patch("/feedback-drafts/{identifier}")
    async def edit_draft(identifier: str, body: DraftPatch, user_id: str = Depends(current_user)):
        changes = body.model_dump(exclude_unset=True, exclude={"revision"})
        if any(value is None for value in changes.values()):
            raise HTTPException(422, "字段不能为 null")
        async with database.sessions.begin() as db:
            result = await db.execute(update(Draft).where(Draft.id == identifier, Draft.user_id == user_id, Draft.revision == body.revision, Draft.status == "draft").values(**changes, revision=Draft.revision + 1))
            if result.rowcount != 1:
                exists = await db.get(Draft, identifier)
                raise HTTPException(409 if exists and exists.user_id == user_id else 404, "草稿已确认、修订已变化或记录不存在")
            return draft_payload(await db.get(Draft, identifier))

    @app.post("/feedback-drafts/{identifier}/confirm")
    async def confirm(identifier: str, body: ConfirmInput, user_id: str = Depends(current_user)):
        return await confirm_draft(identifier, user_id, body.revision)

    @app.get("/feedback")
    async def feedback_list(user_id: str = Depends(current_user)):
        async with database.sessions() as db:
            return [fields(f) for f in await db.scalars(select(Feedback).where(Feedback.user_id == user_id).order_by(Feedback.created_at.desc()))]

    @app.post("/jobs", status_code=202)
    async def submit_job(body: JobInput, user_id: str = Depends(current_user)):
        try:
            return fields(await jobs.create(user_id, body.snapshot_id, body.idempotency_key))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get("/jobs")
    async def list_jobs(user_id: str = Depends(current_user)):
        async with database.sessions() as db:
            return [fields(j) for j in await db.scalars(select(Job).where(Job.user_id == user_id).order_by(Job.created_at.desc()))]

    @app.get("/jobs/{identifier}")
    async def get_job(identifier: str, user_id: str = Depends(current_user)):
        job = await owned(Job, identifier, user_id)
        async with database.sessions() as db:
            attempts = [fields(a) for a in await db.scalars(select(JobAttempt).where(JobAttempt.job_id == identifier))]
        return fields(job) | {"attempt_records": attempts}

    @app.post("/jobs/{identifier}/cancel")
    async def cancel_job(identifier: str, user_id: str = Depends(current_user)):
        await owned(Job, identifier, user_id)
        return fields(await jobs.cancel(identifier))

    @app.get("/internal/qq/deliveries/pending", dependencies=[Depends(bridge_auth)])
    async def pending_deliveries():
        async with database.sessions() as db:
            events = await db.scalars(select(QQEvent).where(QQEvent.status == "ready", QQEvent.delivery_status == "pending").order_by(QQEvent.created_at).limit(100))
            return [{"delivery_id": e.id, "reply": e.reply, "run_id": e.run_id, **e.routing} for e in events]

    @app.post("/internal/qq/deliveries/{identifier}", dependencies=[Depends(bridge_auth)])
    async def delivery(identifier: str, body: DeliveryInput):
        async with database.sessions.begin() as db:
            event = await db.get(QQEvent, identifier)
            if event is None:
                raise HTTPException(404, "投递记录不存在")
            if event.delivery_status in ("sent", "unknown"):
                return {"status": event.delivery_status, "duplicate": True}
            event.delivery_status = body.status
            event.platform_message_id = str(body.platform_message_id) if body.platform_message_id is not None else None
            event.error = body.error
            return {"status": event.delivery_status}

    @app.post("/internal/qq/events", dependencies=[Depends(bridge_auth)])
    async def qq_event(body: QQInput):
        bot, sender = str(body.self_id), str(body.user_id)
        scope = f"group:{body.group_id}" if body.message_type == "group" else f"private:{sender}"
        if bot != config.qq_bot_id or scope not in config.qq_allowlist or sender == bot:
            raise HTTPException(403, "该机器人或会话未加入本次试用白名单")
        if body.message_type == "group" and body.group_id is None:
            raise HTTPException(422, "群事件缺少 group_id")
        namespace = f"qq:{bot}:{scope}:{sender}"
        event_id = hashlib.sha256(f"{namespace}:{body.message_id}".encode()).hexdigest()
        async with database.sessions() as db:
            existing = await db.get(QQEvent, event_id)
            if existing:
                if existing.status == "ready" and existing.delivery_status == "pending":
                    return {"status": "ready", "delivery_id": existing.id, "reply": existing.reply, "run_id": existing.run_id}
                return {"status": "duplicate", "delivery_id": existing.id}
            user = await db.scalar(select(User).where(User.username == namespace))
            if user is None:
                user = User(username=namespace, password_hash=password_hash(secrets.token_urlsafe(32)))
                db.add(user)
                await db.flush()
            session = await db.scalar(select(ChatSession).where(ChatSession.user_id == user.id).order_by(ChatSession.created_at.desc()))
            if session is None:
                session = ChatSession(user_id=user.id, title="QQ 新月杀试用")
                db.add(session)
                await db.flush()
            record = QQEvent(id=event_id, user_id=user.id, session_id=session.id, routing=body.model_dump(exclude={"raw_message", "message_id"}))
            db.add(record)
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                return {"status": "duplicate", "delivery_id": event_id}
        content = re.sub(r"\[CQ:at,qq=\d+\]", "", body.raw_message).strip()
        reply, run_id = "", None
        try:
            confirmation = re.fullmatch(r"确认\s+([A-Fa-f0-9]{8})\s+v(\d+)", content)
            if confirmation:
                async with database.sessions() as db:
                    draft = await db.scalar(select(Draft).where(Draft.short_code == confirmation[1].upper(), Draft.user_id == record.user_id))
                if draft is None:
                    raise HTTPException(404, "没有找到属于你的草稿")
                feedback = await confirm_draft(draft.id, record.user_id, int(confirmation[2]))
                reply = f"反馈已保存，编号 {feedback['id']}；重复确认不会增加记录。"
            elif content.startswith(("反馈", "/反馈")):
                actual = content.removeprefix("/").removeprefix("反馈").strip(" ：:")
                draft = await new_draft(record.user_id, DraftInput(session_id=record.session_id, actual=actual))
                reply = f"反馈草稿 {draft['short_code']} v{draft['revision']}\n实际现象：{actual or '待补充'}\n缺失信息：{', '.join(draft['missing_fields'])}\n核对后发送：确认 {draft['short_code']} v{draft['revision']}"
            else:
                run = await create_run(record.session_id, record.user_id, RunInput(message=content))
                run_id = run.id
                queue = runtime.start(run.id, content)
                while await queue.get() is not None:
                    pass
                async with database.sessions() as db:
                    final = await db.get(Run, run.id)
                reply = final.text if final.status == "completed" else (final.error or "请求已取消")
                if final.citations:
                    reply += "\n依据：" + "；".join(f"{c.get('title', '')}（{c.get('snapshot_id', '')}）" for c in final.citations[:3])
        except HTTPException as error:
            reply = str(error.detail)
        except Exception as error:
            reply = f"处理失败（{type(error).__name__}），请稍后重新提问。"
        async with database.sessions.begin() as db:
            await db.execute(update(QQEvent).where(QQEvent.id == event_id).values(status="ready", reply=reply, run_id=run_id))
        return {"status": "ready", "delivery_id": event_id, "reply": reply, "run_id": run_id}

    return app


app = create_app()
