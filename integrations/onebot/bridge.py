"""The backend owns identities/business state; this process owns platform I/O."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from .config import BridgeConfig, websocket_endpoint
from .events import delivery_target_allowed, normalize_event
from .journal import DeliveryJournal
from .transport import OneBotAPI, SendRejected, SendUnknown

LOG = logging.getLogger("assessment.onebot")


class Bridge:
    def __init__(self, config: BridgeConfig, backend: httpx.AsyncClient,
                 journal: DeliveryJournal, sender: Any):
        self.config, self.backend, self.journal, self.sender = config, backend, journal, sender
        self._delivery_lock = asyncio.Lock()

    async def report(self, delivery_id: str, result: dict[str, Any]) -> None:
        response = await self.backend.post(f"/internal/qq/deliveries/{delivery_id}", json=result)
        response.raise_for_status()

    async def deliver(self, delivery: dict[str, Any]) -> str:
        if not delivery_target_allowed(delivery, self.config):
            return "not_allowed"
        delivery_id, reply = delivery.get("delivery_id"), delivery.get("reply")
        if not isinstance(delivery_id, str) or not delivery_id or not isinstance(reply, str) or not reply.strip():
            return "no_reply"
        async with self._delivery_lock:
            old = self.journal.get(delivery_id)
            if old:
                # Also repairs a lost backend receipt without repeating the platform send.
                if old["status"] in {"sent", "failed", "unknown"}:
                    await self.report(delivery_id, old)
                return "duplicate"
            if not self.journal.reserve(delivery_id):
                return "duplicate"
            try:
                platform_id = await self.sender.send_text(delivery, reply)
                result = {"status": "sent", "platform_message_id": platform_id, "error": None}
            except SendRejected as exc:
                result = {"status": "failed", "platform_message_id": None, "error": str(exc)}
            except SendUnknown as exc:
                result = {"status": "unknown", "platform_message_id": None, "error": str(exc)}
            except Exception as exc:
                result = {"status": "unknown", "platform_message_id": None, "error": type(exc).__name__}
            self.journal.finish(delivery_id, result["status"], result["platform_message_id"], result["error"])
            await self.report(delivery_id, result)
            return result["status"]

    async def handle(self, event: dict[str, Any]) -> str:
        normalized = normalize_event(event, self.config)
        if normalized is None:
            return "ignored"
        response = await self.backend.post("/internal/qq/events", json=normalized)
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict) or not result.get("reply"):
            return str(result.get("status", "no_reply")) if isinstance(result, dict) else "no_reply"
        return await self.deliver({**result, **normalized})

    async def recover_pending(self) -> None:
        response = await self.backend.get("/internal/qq/deliveries/pending")
        if response.status_code == 404:
            return
        response.raise_for_status()
        rows = response.json()
        if isinstance(rows, dict):
            rows = rows.get("items", [])
        for row in rows:
            await self.deliver(row)


async def run_live(config: BridgeConfig) -> None:
    import websockets

    config.validate_live()
    journal = DeliveryJournal(config.state_path)
    headers = {"Authorization": f"Bearer {config.access_token}"}
    backoff = 1.0
    try:
        async with httpx.AsyncClient(
            base_url=config.api_url,
            headers={"X-Bridge-Token": config.bridge_token},
            timeout=config.backend_timeout,
            follow_redirects=False,
        ) as backend:
            while True:
                try:
                    async with (
                        websockets.connect(websocket_endpoint(config.ws_url, "event"), additional_headers=headers,
                                           max_size=65536, max_queue=32) as events,
                        websockets.connect(websocket_endpoint(config.ws_url, "api"), additional_headers=headers,
                                           max_size=65536, max_queue=32) as api,
                    ):
                        bridge = Bridge(config, backend, journal, OneBotAPI(api, config.send_timeout))
                        await bridge.recover_pending()
                        backoff = 1.0
                        async for raw in events:
                            try:
                                event = json.loads(raw)
                                if isinstance(event, dict):
                                    outcome = await bridge.handle(event)
                                    LOG.info("event_processed outcome=%s", outcome)
                            except (ValueError, httpx.HTTPError) as exc:
                                # Logs intentionally contain no raw event, message, account, or token.
                                LOG.warning("event_error type=%s", type(exc).__name__)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    LOG.warning("connection_closed type=%s retry_seconds=%s", type(exc).__name__, backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)
    finally:
        journal.close()
