"""Read-only logical database fingerprints used before and after pg_restore."""
import hashlib
import json


def canonical_row(value: str) -> bytes:
    return json.dumps(json.loads(value), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def assert_quiescent(snapshot: dict):
    if any(snapshot["active"].values()) or snapshot["budget"]["reserved"] != 0:
        raise ValueError("仍有运行、任务、Outbox或未结算费用；拒绝导出/切换")


def assert_same_database(source: dict, target: dict):
    if source["tables"] != target["tables"] or source["budget"] != target["budget"]:
        raise ValueError("迁移后的表数量、内容哈希或费用账本不同，禁止启动真实服务")
    if source["migration"] != target["migration"] or source["pgvector"] != target["pgvector"]:
        raise ValueError("迁移或pgvector版本不一致")
    assert_quiescent(source)
    assert_quiescent(target)


async def fingerprint(connection) -> dict:
    result = {"tables": {}, "active": {}}
    async with connection.transaction(isolation="repeatable_read", readonly=True):
        names = await connection.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
        for row in names:
            name = row["tablename"]
            quoted = '"' + name.replace('"', '""') + '"'
            digest, count = hashlib.sha256(), 0
            query = f'SELECT to_jsonb(t)::text AS row FROM public.{quoted} t ORDER BY to_jsonb(t)::text COLLATE "C"'
            async for item in connection.cursor(query, prefetch=64):
                digest.update(canonical_row(item["row"]) + b"\n")
                count += 1
            result["tables"][name] = {"rows": count, "sha256": digest.hexdigest()}
        result["budget"] = dict(await connection.fetchrow("SELECT id,spent,reserved FROM budget_account WHERE id=1"))
        checks = {"runs": "SELECT count(*) FROM runs WHERE status='running'",
                  "jobs": "SELECT count(*) FROM jobs WHERE status NOT IN ('succeeded','failed','cancelled')",
                  "usage": "SELECT count(*) FROM usage_records WHERE NOT settled",
                  "outbox": "SELECT count(*) FROM outbox WHERE NOT delivered"}
        for key, query in checks.items():
            result["active"][key] = await connection.fetchval(query)
        result["migration"] = await connection.fetchval("SELECT version_num FROM alembic_version")
        result["pgvector"] = await connection.fetchval("SELECT extversion FROM pg_extension WHERE extname='vector'")
        result["postgres"] = await connection.fetchval("SHOW server_version")
    return result

