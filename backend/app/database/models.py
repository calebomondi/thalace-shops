"""Tables. The money itself is in each shop's NEAR Intents Agent API wallet;
these rows are our record of the shops, what they sell and the rules around
them. Invoices, the ledger and owner signatures arrive with their features,
each with its own migration."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    UUID,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agents.schemas.shop import (
    BUYER_KINDS,
    FULL_SHARE_BPS,
    INVOICE_STATUSES,
    LEDGER_KINDS,
    LEDGER_STATUSES,
    MESSAGE_ROLES,
    OFFER_DELIVERIES,
    OFFER_KINDS,
    OFFER_STATUSES,
    PAYEE_ROUTES,
    SHOP_INTENT_STATUSES,
    SHOP_INTENT_TYPES,
    SHOP_SLUG_MAX_LEN,
    SHOP_SLUG_PATTERN,
    SHOP_STATUSES,
)
from app.database.connect import Base

# Asset ids such as "nep141:base-0x8335...02913.omft.near".
ASSET_ID_LEN = 128
# Agent API ids: a 64-hex agent id, "op_…" correlation ids.
API_ID_LEN = 96
# NEAR account ids are at most 64 characters; chain addresses fit in 128.
ADDRESS_LEN = 128


def _one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _now() -> datetime:
    return datetime.now(UTC)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())


def _updated() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, default=_now, server_default=func.now(),
                         onupdate=_now)


class OwnerPasskey(Base):
    """A founder's passkey on one site (its rp_id). Public data only: the
    private key never leaves the founder's device. One passkey owns every shop
    the founder takes live on that site, each with its own wallet."""

    __tablename__ = "owner_passkeys"
    __table_args__ = (UniqueConstraint("user_id", "rp_id", name="uq_owner_passkeys_user_id_rp_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Supabase owns users: no FK. Indexed by the unique constraint, which leads with it.
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    credential_id: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    # P-256 SPKI, base64url: what NEAR Intents checks each signature against.
    public_key: Mapped[str] = mapped_column(String(256), nullable=False)
    rp_id: Mapped[str] = mapped_column(String(253), nullable=False)
    origin: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = _created()


class Shop(Base):
    """A virtual shop: one agent, one wallet, one owner-signed policy."""

    __tablename__ = "shops"
    __table_args__ = (
        CheckConstraint(_one_of("status", SHOP_STATUSES), name="status"),
        CheckConstraint(f"slug ~ '{SHOP_SLUG_PATTERN}'", name="slug_format"),
        CheckConstraint("status = 'draft' OR agent_id IS NOT NULL", name="live_has_agent"),
        CheckConstraint("daily_budget_usd >= 0", name="budget_not_negative"),
        Index("ix_shops_owner_id_created_at", "owner_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Supabase owns users: no FK. Indexed by the created_at index, which leads with it.
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # The public address: /s/<slug>.
    slug: Mapped[str] = mapped_column(String(SHOP_SLUG_MAX_LEN), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    tagline: Mapped[str] = mapped_column(String(200), nullable=False, default="", server_default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    website: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[str] = mapped_column(String(8), nullable=False, default="draft", server_default="draft")
    # What every sale is credited as, whatever the buyer pays with.
    settlement_asset: Mapped[str] = mapped_column(String(ASSET_ID_LEN), nullable=False)
    # The owner's USD cap on what the shop may send out in a day (payouts,
    # fees, purchases). The signed policy enforces it; this is what was signed.
    daily_budget_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # The Agent API agent and its NEAR Intents account, where sales land.
    # Set when the owner signs the shop live.
    agent_id: Mapped[str | None] = mapped_column(String(API_ID_LEN), nullable=True, unique=True)
    wallet_account_id: Mapped[str | None] = mapped_column(String(ADDRESS_LEN), nullable=True)
    # The passkey that signs for the shop's wallet; fixed once the wallet
    # exists. Indexed for "which shops does this passkey own".
    owner_passkey_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("owner_passkeys.id", ondelete="RESTRICT"), nullable=True, index=True)
    # The NEAR account the Agent API derives from that passkey.
    owner_account_id: Mapped[str | None] = mapped_column(String(ADDRESS_LEN), nullable=True)
    policy_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The grant our backend acts under; its token encrypted, never shown or logged.
    grant_id: Mapped[str | None] = mapped_column(String(API_ID_LEN), nullable=True)
    grant_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    grant_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set while the owner's wallet freeze is on: nothing can move money.
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    live_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The last invoice number issued; the next is one more (row-locked).
    invoice_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class Offer(Base):
    """Something a shop sells, at a list price and a floor its agent may not
    go below when negotiating."""

    __tablename__ = "offers"
    __table_args__ = (
        CheckConstraint(_one_of("kind", OFFER_KINDS), name="kind"),
        CheckConstraint(_one_of("delivery", OFFER_DELIVERIES), name="delivery"),
        CheckConstraint(_one_of("status", OFFER_STATUSES), name="status"),
        CheckConstraint("price_cents > 0", name="price_positive"),
        CheckConstraint("floor_cents > 0 AND floor_cents <= price_cents", name="floor_within_price"),
        CheckConstraint("delivery <> 'link' OR delivery_url IS NOT NULL", name="link_has_url"),
        Index("ix_offers_shop_id_status_position", "shop_id", "status", "position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Indexed by the status index, which leads with it.
    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    floor_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    delivery: Mapped[str] = mapped_column(String(10), nullable=False)
    # Private: sent to the buyer once paid, never shown on the shop page.
    delivery_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_note: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    status: Mapped[str] = mapped_column(String(8), nullable=False, default="draft", server_default="draft")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Supabase owns users: no FK. None for an offer the agent drafted.
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class Payee(Base):
    """One share of every sale and where it goes: the revenue split. Each
    address is a destination in the shop's signed policy, so the wallet
    refuses to pay anywhere else."""

    __tablename__ = "payees"
    __table_args__ = (
        CheckConstraint(_one_of("route", PAYEE_ROUTES), name="route"),
        CheckConstraint(f"share_bps > 0 AND share_bps <= {FULL_SHARE_BPS}", name="share_range"),
        CheckConstraint("(route = 'withdraw') = (chain IS NOT NULL)", name="withdraw_has_chain"),
        UniqueConstraint("shop_id", "route", "chain", "address", name="uq_payees_destination",
                         postgresql_nulls_not_distinct=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Indexed by the unique constraint, which leads with it.
    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    route: Mapped[str] = mapped_column(String(10), nullable=False)
    chain: Mapped[str | None] = mapped_column(String(24), nullable=True)
    address: Mapped[str] = mapped_column(String(ADDRESS_LEN), nullable=False)
    memo: Mapped[str | None] = mapped_column(String(128), nullable=True)
    share_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = _created()


class PlatformSettings(Base):
    """The platform's own terms, one row. The fee is set by an admin, never
    above the maximum owners agreed to at go-live; each invoice keeps the fee
    it was issued with."""

    __tablename__ = "platform_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        CheckConstraint(f"max_fee_bps >= 0 AND max_fee_bps <= {FULL_SHARE_BPS}", name="max_fee_range"),
        CheckConstraint("fee_bps >= 0 AND fee_bps <= max_fee_bps", name="fee_within_max"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    fee_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    max_fee_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    # The NEAR account fees are transferred to.
    fee_account: Mapped[str] = mapped_column(String(ADDRESS_LEN), nullable=False)
    # Supabase owns users: no FK. None for the seeded row.
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = _updated()


class AdminAuditLog(Base):
    """Every admin write: who, what, when, and the values before and after."""

    __tablename__ = "admin_audit_log"
    __table_args__ = (Index("ix_admin_audit_log_created_at", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Supabase owns users: no FK.
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    actor_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str] = mapped_column(String(128), nullable=False)
    # Opaque snapshots for the record; nothing filters on them.
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = _created()



class ShopMessage(Base):
    """One message in the owner's conversation with a shop's agent, kept so a
    turn can pick up where the last one ended. Tool calls and results are
    stored as the model saw them."""

    __tablename__ = "shop_messages"
    __table_args__ = (
        CheckConstraint(_one_of("role", MESSAGE_ROLES), name="role"),
        CheckConstraint("role <> 'tool' OR tool_call_id IS NOT NULL", name="tool_has_call_id"),
        Index("ix_shop_messages_shop_id_created_at", "shop_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Indexed by the created_at index, which leads with it.
    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    # Opaque: the model's tool calls, replayed as they were. Nothing filters on them.
    tool_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Supabase owns users: no FK. Set on the owner's own messages.
    author_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = _created()


class ShopIntent(Base):
    """An owner signature a shop is waiting on, generated for one person.
    Only they may submit it: a correlation id from a browser is never trusted
    on its own."""

    __tablename__ = "shop_intents"
    __table_args__ = (
        CheckConstraint(_one_of("type", SHOP_INTENT_TYPES), name="type"),
        CheckConstraint(_one_of("status", SHOP_INTENT_STATUSES), name="status"),
        Index("ix_shop_intents_shop_id_created_at", "shop_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Indexed by the created_at index, which leads with it.
    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(API_ID_LEN), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="awaiting_signature",
                                        server_default="awaiting_signature")
    # Supabase owns users: no FK.
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    # A grant_issue's token, encrypted, until the grant is live on the shop.
    grant_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = _created()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# NEAR Intents amounts are atomic units of up to 128 bits.
ATOMIC = Numeric(40, 0)


class Invoice(Base):
    """One purchase from a shop: what was bought, at what price, and how it
    was paid. A payment address is quoted only when the buyer picks a coin;
    an expired quote is replaced under the same invoice number."""

    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint(_one_of("status", INVOICE_STATUSES), name="status"),
        CheckConstraint(_one_of("buyer_kind", BUYER_KINDS), name="buyer_kind"),
        CheckConstraint("quantity > 0 AND unit_price_cents > 0", name="positive"),
        CheckConstraint("total_cents = quantity * unit_price_cents", name="total"),
        CheckConstraint(f"fee_bps >= 0 AND fee_bps <= {FULL_SHARE_BPS}", name="fee_range"),
        UniqueConstraint("shop_id", "number", name="uq_invoices_shop_id_number"),
        Index("ix_invoices_shop_id_created_at", "shop_id", "created_at"),
        Index("ix_invoices_ip_hash_created_at", "ip_hash", "created_at"),
        Index("ix_invoices_awaiting", "checked_at", postgresql_where=text("status = 'awaiting_payment'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Indexed by the unique constraint and the created_at index, which lead with it.
    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), nullable=False)
    number: Mapped[str] = mapped_column(String(24), nullable=False)
    # The buyer's handle on the invoice (its page), not guessable.
    public_token: Mapped[str] = mapped_column(String(48), nullable=False, unique=True)
    # Offers are archived, never deleted, once anyone bought one.
    offer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offers.id", ondelete="RESTRICT"), nullable=False,
                                                index=True)
    # The line as sold, whatever the offer says later.
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    # The platform fee in force when the invoice was issued; it never changes after.
    fee_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    buyer_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    buyer_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    buyer_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Salted hash of the buyer's IP, to rate limit invoices; never the IP.
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(18), nullable=False, default="open", server_default="open")
    pay_asset: Mapped[str | None] = mapped_column(String(ASSET_ID_LEN), nullable=True)
    # Exactly what the buyer was asked to send, in pay_asset's atomic units.
    pay_amount_raw: Mapped[Decimal | None] = mapped_column(ATOMIC, nullable=True)
    deposit_idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    deposit_correlation_id: Mapped[str | None] = mapped_column(String(API_ID_LEN), nullable=True, unique=True)
    deposit_address: Mapped[str | None] = mapped_column(String(ADDRESS_LEN), nullable=True)
    deposit_memo: Mapped[str | None] = mapped_column(String(128), nullable=True)
    deposit_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # What the shop's wallet was credited, in its settlement asset (amount_out).
    credited_raw: Mapped[Decimal | None] = mapped_column(ATOMIC, nullable=True)
    # On-chain evidence of the payment, and of a refund into the shop's wallet.
    payment_tx_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    refund_tx_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # A written deliverable for the buyer (Markdown), shown on the paid invoice.
    deliverable: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # When the watcher last asked the Agent API about the payment.
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()


class LedgerEntry(Base):
    """One line of a shop's public ledger. Lines are added, and a pending one
    settles; nothing is rewritten. A fee or payout line is written, with its
    idempotency key, before the money is sent, so a retry never pays twice."""

    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint(_one_of("kind", LEDGER_KINDS), name="kind"),
        CheckConstraint(_one_of("status", LEDGER_STATUSES), name="status"),
        CheckConstraint("kind <> 'payout' OR (payee_id IS NOT NULL AND invoice_id IS NOT NULL)",
                        name="payout_has_payee"),
        CheckConstraint("amount_raw >= 0", name="amount_not_negative"),
        UniqueConstraint("invoice_id", "kind", "payee_id", name="uq_ledger_entries_invoice_id_kind_payee_id",
                         postgresql_nulls_not_distinct=True),
        Index("ix_ledger_entries_shop_id_created_at", "shop_id", "created_at"),
        Index("ix_ledger_entries_pending", "shop_id", postgresql_where=text("status = 'pending'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Indexed by the created_at index, which leads with it.
    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), nullable=False)
    # Indexed by the unique constraint, which leads with it.
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"),
                                                         nullable=True)
    payee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payees.id", ondelete="SET NULL"),
                                                       nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False, default="pending", server_default="pending")
    asset: Mapped[str] = mapped_column(String(ASSET_ID_LEN), nullable=False)
    amount_raw: Mapped[Decimal] = mapped_column(ATOMIC, nullable=False)
    # Its USD value when recorded, for totals and the CSV.
    amount_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    # Who it went to or came from, as the ledger shows it.
    counterparty: Mapped[str | None] = mapped_column(String(ADDRESS_LEN), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    correlation_id: Mapped[str | None] = mapped_column(String(API_ID_LEN), nullable=True, unique=True)
    tx_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = _created()
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
