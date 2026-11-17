from sqlalchemy import event, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .config import Settings
from .models import Base, BudgetAccount, User
from .security import password_hash


class Database:
    def __init__(self, settings: Settings):
        options = {}
        if make_url(settings.database_url).drivername == "postgresql+asyncpg":
            import asyncpg
            dsn = make_url(settings.database_url).set(drivername="postgresql").render_as_string(hide_password=False)

            async def connect_postgres():
                # Bare asyncpg DNS/socket errors can bypass SQLAlchemy's normal
                # DBAPI wrapper. Translate at creation, not as global OSError.
                try:
                    return await asyncpg.connect(dsn, timeout=5)
                except OSError as error:
                    raise SQLAlchemyError("数据库连接暂时不可用") from error

            options["async_creator"] = connect_postgres
        self.engine = create_async_engine(settings.database_url, pool_pre_ping=True, **options)
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
