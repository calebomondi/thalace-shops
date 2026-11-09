"""The vocabulary of a shop, shared by the agents, the API and the database
constraints. One source of truth: the database CHECK constraints are built
from these tuples."""

from typing import Literal

# draft: being set up, nothing on sale, no wallet yet. live: selling.
# paused: new invoices stopped on our side. The wallet's own freeze is
# separate (shops.frozen_at), because only the owner's signature sets it.
ShopStatus = Literal["draft", "live", "paused"]
SHOP_STATUSES: tuple[str, ...] = ShopStatus.__args__

# digital: a file, link or report. service: work the shop does, including
# made-to-order physical work the team delivers.
OfferKind = Literal["digital", "service"]
OFFER_KINDS: tuple[str, ...] = OfferKind.__args__
# How a paid invoice is fulfilled: a private link, a Markdown deliverable
# written for the buyer, or a service the team marks done.
OfferDelivery = Literal["link", "markdown", "service"]
OFFER_DELIVERIES: tuple[str, ...] = OfferDelivery.__args__
# draft: written (by the owner, or drafted by the agent) and not on sale yet.
OfferStatus = Literal["draft", "active", "archived"]
OFFER_STATUSES: tuple[str, ...] = OfferStatus.__args__

# Where a payee's share goes: another NEAR Intents account (transfer), or out
# to an address on a chain (withdraw). Both must be in the signed policy.
PayeeRoute = Literal["transfer", "withdraw"]
PAYEE_ROUTES: tuple[str, ...] = PayeeRoute.__args__

# Basis points: shares and fees. 10_000 = 100%.
FULL_SHARE_BPS = 10_000
SHOP_SLUG_PATTERN = "^[a-z0-9](?:[a-z0-9-]{1,46}[a-z0-9])$"
SHOP_SLUG_MAX_LEN = 48
