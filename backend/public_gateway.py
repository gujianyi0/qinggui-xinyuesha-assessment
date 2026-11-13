"""Narrow owner-hosted relay. It never reads the provider key or starts an Agent."""
import base64
import hashlib
import hmac
import json
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from .app.public_schemas import PublicIdentity


class GatewayConfig(BaseModel):
    origin: str = "http://127.0.0.1:18081"
    edge_token: str = Field(min_length=43, repr=False)
    service_token: str = Field(min_length=43, repr=False)
    signing_key: str = Field(min_length=43, repr=False)


def sign_token(payload: dict, key: str) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    return encoded + "." + hmac.new(key.encode(), encoded.encode(), hashlib.sha256).hexdigest()


def decode_token(raw: str, key: str) -> dict:
    try:
        encoded, signature = raw.split(".")
        expected = hmac.new(key.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if payload["exp"] <= time.time() or not payload["user_id"].startswith("public:"):
            raise ValueError
        return payload
    except (ValueError, KeyError, TypeError):
        raise HTTPException(401, "访客登录已失效，请重新进入") from None


def allowed(method: str, path: str) -> bool:
    identifier = r"[a-f0-9-]{36}"
    routes = {
        "GET": [r"/health", r"/sessions", rf"/sessions/{identifier}/messages", rf"/runs/{identifier}", rf"/sessions/{identifier}/requests/{identifier}",
                r"/catalog/(snapshots|entities|rulings)", r"/feedback-drafts", r"/feedback"],
        "POST": [r"/sessions", rf"/sessions/{identifier}/runs", rf"/sessions/{identifier}/submissions", rf"/runs/{identifier}/cancel",
                 rf"/sessions/{identifier}/requests/{identifier}/cancel",
                 r"/feedback-drafts", rf"/feedback-drafts/{identifier}/confirm"],
        "PATCH": [rf"/feedback-drafts/{identifier}"],
    }
    return any(re.fullmatch(pattern, path) for pattern in routes.get(method, []))


def create_gateway(config: GatewayConfig, transport=None):

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(base_url=config.origin, timeout=35, trust_env=False, transport=transport) as client:
            app.state.client = client
            yield

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.middleware("http")
    async def guard(request, call_next):
        if not hmac.compare_digest(request.headers.get("x-public-edge", ""), config.edge_token):
            return JSONResponse({"detail": "入口身份无效"}, status_code=401)
        try:
            response = await call_next(request)
        except httpx.HTTPError:
            response = JSONResponse({"detail": "本机问答服务暂时不可用，请稍后重试"}, status_code=503)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PATCH", "PUT", "DELETE"])
    async def relay(path: str, request: Request):
        route = "/" + path
        if not allowed(request.method, route) and not (route == "/auth/guest" and request.method == "POST"):
            raise HTTPException(404, "接口不存在")
        # Enforce the actual streamed size; Content-Length alone is untrusted.
        parts, size = [], 0
        async for part in request.stream():
            size += len(part)
            if size > 48000:
                raise HTTPException(413, "提交内容过长")
            parts.append(part)
        body = b"".join(parts)
        headers = {"Content-Type": "application/json"}
        if route == "/auth/guest":
            try:
                identity = PublicIdentity.model_validate_json(body)
            except ValueError:
                raise HTTPException(422, "访客标识无效") from None
            upstream = await app.state.client.post("/internal/public/identity", content=identity.model_dump_json(),
                                                   headers={"X-Public-Service": config.service_token, **headers})
            if upstream.status_code != 200:
                return Response(upstream.content, upstream.status_code, media_type="application/json")
            result = upstream.json()
            result["access_token"] = sign_token({"upstream": result["access_token"], "user_id": result["user"]["id"],
                                                 "exp": int(time.time()) + 43200}, config.signing_key)
            return result
        token = decode_token(request.headers.get("authorization", "").removeprefix("Bearer "), config.signing_key)
        headers["Authorization"] = "Bearer " + token["upstream"]
        if request.method == "POST" and re.fullmatch(r"/sessions/[a-f0-9-]{36}/(?:runs|submissions)", route):
            route = "/internal/public" + route.replace('/submissions', '/runs')
            headers["X-Public-Service"] = config.service_token
        upstream = await app.state.client.request(request.method, route, content=body, params=request.query_params, headers=headers)
        if route == "/health" and upstream.status_code == 200:
            health = upstream.json()
            return {key: value for key, value in health.items() if key in ("status", "model_mode", "snapshot_id", "index_published")}
        return Response(upstream.content, upstream.status_code, media_type="application/json")

    return app


def application():
    return create_gateway(GatewayConfig.model_validate_json(Path(".local/public-entry/config.json").read_text(encoding="utf-8")))
