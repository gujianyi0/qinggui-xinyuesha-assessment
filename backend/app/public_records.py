"""Explicitly opted-in owner records; public readers never acquire ownership."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from .models import ChatSession, Draft, Feedback, Message, User


def records_router(database, settings, current_user, service_auth):
    router = APIRouter(prefix='/internal/public/shared', dependencies=[Depends(service_auth)])

    async def shared_owner(user_id: str = Depends(current_user)):
        if not user_id.startswith('public:'):
            raise HTTPException(403, '共享检阅需要访客身份')
        async with database.sessions() as db:
            owner = await db.scalar(select(User).where(User.username == settings.public_shared_username))
        if not settings.public_shared_username or owner is None:
            raise HTTPException(404, '主人尚未公开历史记录')
        return owner.id

    def clean(value):
        if isinstance(value, str):
            for secret in (settings.model_api_key, settings.public_service_token, settings.bookshelf_owner_key, settings.bridge_token):
                if secret:
                    value = value.replace(secret, '[凭据已隐藏]')
            return value
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items()}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    def payload(items, total, offset, limit):
        return {'items': clean(items), 'total': total, 'offset': offset, 'limit': limit, 'readonly': True}

    @router.get('/sessions')
    async def sessions(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=50), owner: str = Depends(shared_owner)):
        async with database.sessions() as db:
            condition = ChatSession.user_id == owner
            total = await db.scalar(select(func.count()).select_from(ChatSession).where(condition))
            rows = await db.scalars(select(ChatSession).where(condition).order_by(ChatSession.created_at.desc(), ChatSession.id).offset(offset).limit(limit))
            return payload([{'id': row.id, 'title': row.title, 'created_at': row.created_at} for row in rows], total, offset, limit)

    @router.get('/sessions/{identifier}/messages')
    async def messages(identifier: str, offset: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=20), owner: str = Depends(shared_owner)):
        async with database.sessions() as db:
            session = await db.get(ChatSession, identifier)
            if session is None or session.user_id != owner:
                raise HTTPException(404, '公开会话不存在')
            condition = Message.session_id == identifier
            total = await db.scalar(select(func.count()).select_from(Message).where(condition))
            rows = await db.scalars(select(Message).where(condition).order_by(Message.created_at, Message.id).offset(offset).limit(limit))
            return payload([{'id': row.id, 'role': row.role, 'content': row.content, 'citations': row.citations, 'created_at': row.created_at} for row in rows], total, offset, limit)

    @router.get('/feedback')
    async def feedback(kind: str = Query('submitted', pattern='^(drafts|submitted)$'), offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=50), owner: str = Depends(shared_owner)):
        model = Draft if kind == 'drafts' else Feedback
        async with database.sessions() as db:
            condition = model.user_id == owner
            total = await db.scalar(select(func.count()).select_from(model).where(condition))
            rows = await db.scalars(select(model).where(condition).order_by(model.created_at.desc(), model.id).offset(offset).limit(limit))
            items = []
            keys = ('category', 'actual', 'expected', 'steps', 'context', 'platform', 'client_version')
            for row in rows:
                record = {key: getattr(row, key) for key in ('id', 'revision', 'created_at')}
                record['status'] = row.status if kind == 'drafts' else 'submitted'
                record['payload'] = {key: getattr(row, key) for key in keys} if kind == 'drafts' else {key: row.payload.get(key, '') for key in keys}
                items.append(record)
            return payload(items, total, offset, limit)

    return router
