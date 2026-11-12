from uuid import UUID

from pydantic import Field

from .schemas import RunInput, StrictModel


class PublicIdentity(StrictModel):
    client_secret: str = Field(min_length=43, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class PublicRunInput(RunInput):
    request_id: UUID
