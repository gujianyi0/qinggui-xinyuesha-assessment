"""Container-side isolated evaluation seed and owner-ledger allowance settlement."""
import argparse
import asyncio
import json
import re

from sqlalchemy import select, text
from sqlalchemy.engine import make_url

from backend.app.budget_grants import reserve_grant, settle_grant
from backend.app.config import Settings
from backend.app.db import Database
from backend.app.models import BudgetAccount, BudgetGrant, IndexedChunk, Job, PublishedIndex, Run, UsageRecord, User


async def execute(operation, name):
    if not re.fullmatch(r'assessment_eval_[a-z0-9_]{1,40}', name):
        raise ValueError('Evaluation must use a dedicated database name')
    settings = Settings()
    owner = Database(settings)
    isolated_settings = settings.model_copy(update={
        'database_url': make_url(settings.database_url).set(database=name).render_as_string(hide_password=False),
        'create_schema': False, 'seed_users': True,
    })
    isolated = Database(isolated_settings)
    try:
        if operation == 'seed':
            grant = await reserve_grant(owner, name, 30, settings.total_budget_cny,
                                        {'database': name, 'purpose': 'v1.9 fixed real evaluations'})
            if grant.status != 'reserved':
                raise ValueError('Settled evaluation cannot be restarted with a fresh allowance')
            await isolated.initialize(isolated_settings)
            async with owner.sessions() as source, isolated.sessions.begin() as target:
                if await target.scalar(select(PublishedIndex)):
                    raise ValueError('Evaluation already seeded; preserve its ledger and use existing container')
                account = await target.get(BudgetAccount, 1)
                if account.spent or account.reserved:
                    raise ValueError('Evaluation already has usage; never reset its ledger')
                alice = await target.scalar(select(User).where(User.username == 'alice'))
                indexes = list(await source.scalars(select(PublishedIndex)))
                count = 0
                for index in indexes:
                    job = await source.get(Job, index.job_id)
                    if job.status != 'succeeded':
                        raise ValueError('Only published successful public indexes can be copied')
                    values = {col.name: getattr(job, col.name) for col in Job.__table__.columns}
                    values['user_id'] = alice.id
                    await target.execute(Job.__table__.insert().values(**values))
                    chunks = list(await source.scalars(select(IndexedChunk).where(
                        IndexedChunk.job_id == index.job_id, IndexedChunk.generation == index.generation)))
                    for chunk in chunks:
                        values = {col.name: getattr(chunk, col.name) for col in IndexedChunk.__table__.columns}
                        await target.execute(IndexedChunk.__table__.insert().values(**values))
                        await target.execute(text('INSERT INTO vector_chunks(chunk_id,job_id,generation,embedding) '
                                                  'VALUES (:id,:job,:generation,CAST(:vector AS vector))'),
                                             {'id': chunk.id, 'job': chunk.job_id, 'generation': chunk.generation,
                                              'vector': json.dumps(chunk.embedding)})
                    await target.execute(PublishedIndex.__table__.insert().values(**{
                        col.name: getattr(index, col.name) for col in PublishedIndex.__table__.columns}))
                    count += len(chunks)
                if not indexes or not count:
                    raise ValueError('No indexed public sources to evaluate')
            print(json.dumps({'seeded': True, 'public_chunks': count, 'reserved_owner_cny': 30,
                              'private_sessions_copied': False, 'database': name}))
        elif operation == 'settle':
            async with isolated.sessions() as db:
                if await db.scalar(select(Run).where(Run.status == 'running')):
                    raise ValueError('Evaluation still has active runs')
                if await db.scalar(select(UsageRecord).where(UsageRecord.settled.is_(False))):
                    raise ValueError('Evaluation still has unsettled charges')
                account = await db.get(BudgetAccount, 1)
                if abs(account.reserved) > 1e-8:
                    raise ValueError('Evaluation still has reserved charges')
                cost = account.spent
            grant = await settle_grant(owner, name, cost)
            async with owner.sessions() as db:
                account = await db.get(BudgetAccount, 1)
                receipt = await db.get(BudgetGrant, name)
                assert receipt.status == 'settled'
                print(json.dumps({'settled': True, 'database': name, 'charged_cny': grant.charged,
                                  'owner_spent_cny': account.spent, 'owner_reserved_cny': account.reserved}))
    finally:
        await isolated.close()
        await owner.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['seed', 'settle'])
    parser.add_argument('--database', required=True)
    args = parser.parse_args()
    asyncio.run(execute(args.operation, args.database))
