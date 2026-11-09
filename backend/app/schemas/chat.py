import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatMessageOut(BaseModel):
    id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    # The agent's tools used since the owner last spoke (e.g. read_website).
    actions: list[str]
    created_at: datetime
