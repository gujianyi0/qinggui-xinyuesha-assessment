from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .config import Settings
from .models import Base, BudgetAccount, User
from .security import password_hash


class Database:
    def __init__(self, settings: Settings):
        self.engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        if settings.database_url.startswith("sqlite"):
            @event.listens_for(self.engine.sync_engine, "connect")
            def configure_sqlite(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA busy_timeout=10000")
                connection.execute("PRAGMA journal_mode=WAL")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def initialize(self, settings: Settings):
        if settings.create_schema:
            async with self.engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
        async with self.sessions.begin() as db:
            if await db.get(BudgetAccount, 1) is None:
                db.add(BudgetAccount(id=1, spent=0, reserved=0))
            if settings.seed_users:
                for username in ("alice", "bob"):
                    if not await db.scalar(select(User).where(User.username == username)):
                        db.add(User(username=username, password_hash=password_hash(settings.demo_password)))

    async def close(self):
        await self.engine.dispose()
