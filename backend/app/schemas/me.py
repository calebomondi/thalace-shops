import uuid

from pydantic import BaseModel


class MeOut(BaseModel):
    id: uuid.UUID
    email: str | None
    name: str | None
    is_admin: bool
