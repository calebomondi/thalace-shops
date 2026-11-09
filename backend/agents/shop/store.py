"""The shop agent's only way to the shop's data. The backend implements it,
scoped to one shop, so agents/ never imports the app or the database.

Nothing here can change payees, the daily cap, a price floor on an offer for
sale, the allowed suppliers, or put an offer on sale: those are the owner's,
and the store has no method for them. Buying spends from the shop's wallet
only within its signed policy (allowed suppliers, daily cap)."""

from typing import Protocol
from uuid import UUID

from agents.schemas.agent import (
    GroupOrderView,
    MarketShop,
    OfferDraft,
    OfferView,
    Purchase,
    SalesSummary,
    ShopView,
)


class ShopNotFoundError(Exception):
    """The offer or shop the agent named doesn't exist (or isn't this shop's)."""


class DraftOnlyError(Exception):
    """The agent tried to change an offer that is on sale or archived."""


class PurchaseRefusedError(Exception):
    """A purchase or join was refused; the message says why, for the model."""


class ShopStore(Protocol):
    async def shop(self) -> ShopView: ...

    async def offers(self) -> list[OfferView]: ...

    async def draft_offer(self, draft: OfferDraft) -> OfferView: ...

    async def update_draft(self, offer_id: UUID, draft: OfferDraft) -> OfferView:
        """Rewrite a draft. Raises DraftOnlyError for an offer that is on sale."""
        ...

    async def sales(self) -> SalesSummary: ...

    async def find_suppliers(self, query: str) -> list[MarketShop]: ...

    async def buy(self, offer_id: UUID, quantity: int) -> Purchase:
        """Buy from an allowed supplier, paid from the shop's wallet. Raises PurchaseRefusedError."""
        ...

    async def open_group_orders(self) -> list[GroupOrderView]: ...

    async def join_group_order(self, group_order_id: str, quantity: int) -> GroupOrderView:
        """Join as this shop; its invoice is paid from the wallet at the close. Raises PurchaseRefusedError."""
        ...
