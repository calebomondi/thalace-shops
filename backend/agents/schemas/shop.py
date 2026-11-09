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

# Who wrote a message in the owner's conversation with the shop's agent.
MessageRole = Literal["user", "assistant", "tool"]
MESSAGE_ROLES: tuple[str, ...] = MessageRole.__args__

# What the owner's passkey signs for a shop, through the Agent API.
ShopIntentType = Literal["agent_create", "grant_issue", "policy_update", "agent_freeze", "agent_unfreeze"]
SHOP_INTENT_TYPES: tuple[str, ...] = ShopIntentType.__args__
ShopIntentStatus = Literal["awaiting_signature", "submitted", "succeeded", "failed", "expired"]
SHOP_INTENT_STATUSES: tuple[str, ...] = ShopIntentStatus.__args__

# open: issued, no payment address yet. awaiting_payment: an address is
# quoted for the exact amount. paid: it arrived. delivered: the buyer has it.
# expired: the quote ran out unpaid (pay again under the same number).
# refunded: what arrived couldn't be credited as sent; it went back into the
# shop's own wallet, never to the buyer. failed: no address could be made.
InvoiceStatus = Literal["open", "awaiting_payment", "paid", "delivered", "expired", "refunded", "failed"]
INVOICE_STATUSES: tuple[str, ...] = InvoiceStatus.__args__
# Who an invoice is for: a person on the shop page, an outside agent, or another shop.
BuyerKind = Literal["person", "agent", "shop"]
BUYER_KINDS: tuple[str, ...] = BuyerKind.__args__

# The public ledger. sale: a payment credited. fee: the platform's share,
# sent to its account. payout: a payee's share. refund: money sent back.
LedgerKind = Literal["sale", "fee", "payout", "refund"]
LEDGER_KINDS: tuple[str, ...] = LedgerKind.__args__
LedgerStatus = Literal["pending", "done", "failed"]
LEDGER_STATUSES: tuple[str, ...] = LedgerStatus.__args__

# A negotiation over one offer. open: moves are being made. agreed: both
# sides settled on a unit price, which an invoice can be issued at.
# walked_away: one side ended it. invoiced: the agreed price was invoiced.
NegotiationStatus = Literal["open", "agreed", "walked_away", "invoiced"]
NEGOTIATION_STATUSES: tuple[str, ...] = NegotiationStatus.__args__
NegotiationSide = Literal["buyer", "seller"]
NEGOTIATION_SIDES: tuple[str, ...] = NegotiationSide.__args__
# offer: the buyer names a price. counter: the seller names one. accept:
# take the other side's last price. walk_away: end without a deal.
NegotiationMove = Literal["offer", "counter", "accept", "walk_away"]
NEGOTIATION_MOVES: tuple[str, ...] = NegotiationMove.__args__

# open: taking members until its deadline. closed: the price was locked at
# the tier reached and each member was invoiced. cancelled: closed empty.
GroupOrderStatus = Literal["open", "closed", "cancelled"]
GROUP_ORDER_STATUSES: tuple[str, ...] = GroupOrderStatus.__args__
