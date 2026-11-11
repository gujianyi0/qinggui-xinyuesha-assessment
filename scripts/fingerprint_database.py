"""Print counts and hashes, never row content or connection credentials."""
import asyncio
import json

import asyncpg
from sqlalchemy.engine import make_url

from backend.app.config import Settings
from backend.app.database_transfer import fingerprint


async def main():
    dsn = make_url(Settings().database_url).set(drivername="postgresql").render_as_string(hide_password=False)
    connection = await asyncpg.connect(dsn, timeout=5)
    try:
        print(json.dumps(await fingerprint(connection), ensure_ascii=False))
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(main())
