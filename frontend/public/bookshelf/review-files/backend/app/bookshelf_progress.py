"""Reuse the original shared shelf progress without exposing its owner key."""
import asyncio

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from .config import Settings

LEARNING_IDS = frozenset(f'{group}-{item:02d}' for group, count in enumerate([6, 9, 8, 5, 7, 7, 7], 1)
                         for item in range(1, count + 1))


class MasteryInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    learned: StrictBool
    revision: int = Field(ge=0, strict=True)


class ShelfProgress:
    def __init__(self, settings: Settings):
        self.settings = settings

    def client(self):
        return httpx.AsyncClient(base_url=self.settings.bookshelf_progress_url, timeout=12, trust_env=False,
                                 proxy=self.settings.bookshelf_http_proxy or None,
                                 headers={'Origin': self.settings.bookshelf_progress_url.rstrip('/')})

    def snapshot(self, response: httpx.Response, can_edit: bool):
        if response.status_code == 409:
            raise HTTPException(409, '共享进度已由其他页面更新，请刷新后重试')
        if response.status_code != 200:
            raise HTTPException(503, '共享进度暂时不可用，原有记录未清空')
        try:
            value = response.json()
            if (not isinstance(value.get('ids'), list) or not all(isinstance(i, str) and i in LEARNING_IDS for i in value['ids'])
                    or type(value.get('revision')) is not int or value['revision'] < 0
                    or type(value.get('initialized')) is not bool):
                raise ValueError('invalid shared snapshot')
            return {'ids': sorted(set(value['ids'])), 'revision': value['revision'], 'initialized': value['initialized'],
                    'updatedAt': value.get('updatedAt'), 'can_edit': can_edit}
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(502, '共享进度响应无效，原有记录未清空') from None

    async def read(self, can_edit: bool):
        try:
            async with asyncio.timeout(12), self.client() as client:
                for attempt in range(2):
                    try:
                        response = await client.get('/api/progress', timeout=5)
                        if response.status_code >= 500 and attempt == 0:
                            await asyncio.sleep(0.2)
                            continue
                        return self.snapshot(response, can_edit)
                    except httpx.HTTPError:
                        if attempt:
                            raise
                        await asyncio.sleep(0.2)
        except (httpx.HTTPError, TimeoutError):
            raise HTTPException(503, '共享进度连接失败，原有记录未清空') from None

    async def write(self, body: MasteryInput):
        if body.id not in LEARNING_IDS:
            raise HTTPException(422, '仅知识文档可以记录掌握进度，考核资料不计入')
        if not self.settings.bookshelf_owner_key:
            raise HTTPException(503, '共享进度管理尚未配置')
        try:
            async with asyncio.timeout(12), self.client() as client:
                login = await client.post('/api/session', json={'key': self.settings.bookshelf_owner_key})
                if login.status_code != 200:
                    raise HTTPException(503, '共享进度管理身份暂时不可用')
                return self.snapshot(await client.patch('/api/progress', json=body.model_dump()), True)
        except (httpx.HTTPError, TimeoutError):
            raise HTTPException(503, '共享进度更新未确认，请刷新核对原记录') from None
