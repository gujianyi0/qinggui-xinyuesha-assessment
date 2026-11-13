"""Reserve a bounded evaluation allowance in the authoritative owner's ledger."""
import math

from sqlalchemy import select

from .models import BudgetAccount, BudgetGrant, now


async def reserve_grant(database, identifier: str, amount: float, limit: float, details: dict):
    if not math.isfinite(amount) or not 0 < amount <= limit <= 200:
        raise ValueError('Invalid evaluation allowance')
    async with database.sessions.begin() as db:
        account = await db.scalar(select(BudgetAccount).where(BudgetAccount.id == 1).with_for_update())
        existing = await db.get(BudgetGrant, identifier)
        if existing:
            if existing.amount != amount or existing.details != details:
                raise ValueError('Existing allowance belongs to a different evaluation')
            return existing
        if account.spent + account.reserved + amount > limit:
            raise ValueError('Insufficient owner budget')
        account.reserved += amount
        grant = BudgetGrant(id=identifier, amount=amount, charged=0, status='reserved', details=details)
        db.add(grant)
        await db.flush()
        return grant


async def settle_grant(database, identifier: str, charged: float):
    if not math.isfinite(charged) or charged < 0:
        raise ValueError('Invalid evaluation cost')
    async with database.sessions.begin() as db:
        account = await db.scalar(select(BudgetAccount).where(BudgetAccount.id == 1).with_for_update())
        grant = await db.scalar(select(BudgetGrant).where(BudgetGrant.id == identifier).with_for_update())
        if grant is None or charged > grant.amount:
            raise ValueError('Missing allowance or cost exceeds reserved allowance')
        if grant.status == 'settled':
            if abs(grant.charged - charged) > 1e-8:
                raise ValueError('Settled allowance cannot be silently changed')
            return grant
        account.reserved -= grant.amount
        account.spent += charged
        grant.charged, grant.status, grant.settled_at = charged, 'settled', now()
        return grant
