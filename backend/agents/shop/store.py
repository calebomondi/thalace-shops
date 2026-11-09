"""The shop agent's only way to the shop's data. The backend implements it,
scoped to one shop, so agents/ never imports the app or the database.

Nothing here can change payees, the daily cap, a price floor on an offer for
sale, or put an offer on sale: those are the owner's, and the store has no
method for them."""

from typing import Protocol
from uuid import UUID

from agents.schemas.agent import OfferDraft, OfferView, ShopView


class ShopNotFoundError(Exception):
    """The offer or shop the agent named doesn't exist (or isn't this shop's)."""


class DraftOnlyError(Exception):
    """The agent tried to change an offer that is on sale or archived."""


class ShopStore(Protocol):
    async def shop(self) -> ShopView: ...

    async def offers(self) -> list[OfferView]: ...

    async def draft_offer(self, draft: OfferDraft) -> OfferView: ...

    async def update_draft(self, offer_id: UUID, draft: OfferDraft) -> OfferView:
        """Rewrite a draft. Raises DraftOnlyError for an offer that is on sale."""
        ...
