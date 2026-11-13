import pytest
from sqlalchemy import select

from backend.app.budget_grants import reserve_grant, settle_grant
from backend.app.models import BudgetAccount


async def test_evaluation_allowance_is_bounded_idempotent_and_settled_once(app):
    database = app.state.database
    await reserve_grant(database, 'v19-isolated', 30, 200, {'database': 'isolated'})
    await reserve_grant(database, 'v19-isolated', 30, 200, {'database': 'isolated'})
    with pytest.raises(ValueError):
        await reserve_grant(database, 'other', 180, 200, {})
    with pytest.raises(ValueError):
        await reserve_grant(database, 'v19-isolated', 29, 200, {'database': 'isolated'})
    with pytest.raises(ValueError):
        await settle_grant(database, 'v19-isolated', 31)
    await settle_grant(database, 'v19-isolated', .75)
    await settle_grant(database, 'v19-isolated', .75)
    with pytest.raises(ValueError):
        await settle_grant(database, 'v19-isolated', .80)
    async with database.sessions() as db:
        account = await db.scalar(select(BudgetAccount))
        assert account.reserved == 0 and account.spent == .75


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -1, 201])
async def test_invalid_allowance_is_rejected(app, value):
    with pytest.raises(ValueError):
        await reserve_grant(app.state.database, 'invalid', value, 200, {})
