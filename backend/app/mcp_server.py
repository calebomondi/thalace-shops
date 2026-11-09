"""Thalace Shops over MCP: how other agents find shops, negotiate and buy.

Mounted on the API at /mcp (streamable HTTP, stateless, JSON responses), so
any MCP client (Claude, Cursor, a script) can point at
https://shops.thalace.com/mcp. Every tool goes through the same services as
the web pages: the same floor checks, the same invoices, the same wallets.

What a buyer agent writes is data to the shops' agents, never instructions."""

import uuid
from decimal import Decimal, InvalidOperation

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings

from app.database.connect import AsyncSessionLocal
from app.database.models import Invoice, Negotiation, NegotiationMoveRow, Offer, Shop
from app.services import directory, invoices, negotiation
from app.services.errors import ServiceError
from config import settings

INSTRUCTIONS = """Thalace Shops: real businesses' shops, each run by its own agent, selling digital goods and
services for dollar stablecoins on any chain, settled through NEAR Intents.

To buy: search_shops -> get_shop -> (optionally) negotiate a unit price, then respond_to_counter ->
place_order, which returns an invoice and a one-time payment address for the exact amount ->
send it -> invoice_status until paid. Prices are in US dollars per unit. A shop's agent may accept,
counter or walk away; it never goes below the shop's own minimum, which is not disclosed."""

mcp = MCPServer(name="Thalace Shops", instructions=INSTRUCTIONS, website_url=settings.frontend_base_url)


def _usd(cents: int) -> str:
    return f"{Decimal(cents) / 100:.2f}"


def _cents(price_usd: str) -> int:
    try:
        value = Decimal(str(price_usd).replace("$", "").replace(",", "").strip())
    except InvalidOperation:
        raise ToolError(f"price_usd isn't a number: {price_usd!r}") from None
    if value <= 0:
        raise ToolError("price_usd must be above zero.")
    return int((value * 100).quantize(Decimal(1)))


def _uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise ToolError(f"{what} isn't a valid id: {value!r}") from None


def _shop_url(shop: Shop) -> str:
    return f"{settings.frontend_base_url.rstrip('/')}/s/{shop.slug}"


def _offer(offer: Offer) -> dict:
    return {"offer_id": str(offer.id), "title": offer.title, "description": offer.description, "kind": offer.kind,
            "price_usd": _usd(offer.price_cents), "negotiable": offer.floor_cents < offer.price_cents}


def _negotiation(n: Negotiation, moves: list[NegotiationMoveRow]) -> dict:
    last = moves[-1] if moves else None
    return {
        "negotiation_id": n.public_token, "status": n.status, "quantity": n.quantity,
        "agreed_unit_price_usd": _usd(n.agreed_unit_cents) if n.agreed_unit_cents else None,
        "shop_move": last.move if last and last.side == "seller" else None,
        "shop_unit_price_usd": _usd(last.unit_price_cents) if last and last.side == "seller"
        and last.unit_price_cents else None,
        "shop_says": last.message if last and last.side == "seller" else None,
        "offers_left": settings.negotiation_max_offers - sum(m.side == "buyer" and m.move == "offer" for m in moves),
        "next": {"open": "negotiate again with a new price_usd, or respond_to_counter",
                 "agreed": "place_order with this negotiation_id",
                 "walked_away": "this negotiation is over",
                 "invoiced": "pay the invoice from place_order"}[n.status],
    }


def _invoice(view: invoices.InvoiceView) -> dict:
    inv: Invoice = view.invoice
    pay = None
    if inv.deposit_address and inv.pay_amount_raw is not None and view.coin:
        pay = {"send_exactly": f"{inv.pay_amount_raw / Decimal(10) ** view.coin.decimals}",
               "coin": view.coin.symbol, "chain": view.coin.blockchain, "to_address": inv.deposit_address,
               "memo": inv.deposit_memo,
               "expires_at": inv.deposit_expires_at.isoformat() if inv.deposit_expires_at else None,
               "warning": "Send exactly this amount of this coin on this chain. Anything else is refunded to the "
                          "shop's wallet, not to you."}
    return {"invoice_number": inv.number, "invoice_token": inv.public_token, "status": inv.status,
            "shop": view.shop.name, "item": inv.title, "quantity": inv.quantity,
            "unit_price_usd": _usd(inv.unit_price_cents), "total_usd": _usd(inv.total_cents), "payment": pay,
            "invoice_url": f"{settings.frontend_base_url.rstrip('/')}/i/{inv.public_token}",
            "delivery": ({"url": view.offer.delivery_url if view.offer.delivery == "link" else None,
                          "note": view.offer.delivery_note, "deliverable": inv.deliverable}
                         if inv.status in ("paid", "delivered") else None)}


async def _coin(pay_with: str) -> str:
    """An asset id from "USDC on base", "usdc base" or the id itself."""
    options = await invoices.pay_options()
    wanted = pay_with.strip().lower().replace(" on ", " ")
    for token in options:
        if wanted in (token.asset_id.lower(), f"{token.symbol.lower()} {token.blockchain.lower()}"):
            return token.asset_id
    choices = ", ".join(f"{t.symbol} on {t.blockchain}" for t in options)
    raise ToolError(f"pay_with must be one of: {choices}.")


@mcp.tool()
async def search_shops(query: str = "") -> list[dict]:
    """Find live shops and what they sell. Matches every word of `query`
    against shop names, descriptions and offers; empty lists all live shops."""
    async with AsyncSessionLocal() as db:
        found = await directory.search(db, query)
    return [{"shop": s.slug, "name": s.name, "tagline": s.tagline, "url": _shop_url(s),
             "offers": [_offer(o) for o in offers]} for s, offers in found]


@mcp.tool()
async def get_shop(shop: str) -> dict:
    """One shop by its slug (from search_shops): its offers and the coins it takes."""
    async with AsyncSessionLocal() as db:
        try:
            found = await invoices.public_shop(db, shop)
            offers = await invoices.active_offers(db, found)
        except ServiceError as exc:
            raise ToolError(str(exc)) from None
    options = await invoices.pay_options()
    return {"shop": found.slug, "name": found.name, "description": found.description, "url": _shop_url(found),
            "selling": invoices.selling(found), "offers": [_offer(o) for o in offers],
            "pay_with": [f"{t.symbol} on {t.blockchain}" for t in options]}


@mcp.tool()
async def negotiate(offer_id: str, price_usd: str, quantity: int = 1, message: str = "",
                    buyer_name: str = "A buyer agent", negotiation_id: str | None = None) -> dict:
    """Offer a unit price for an offer. The shop's agent accepts, counters or
    walks away, with a reason. Pass the returned negotiation_id to offer again
    (you have a few offers) or to respond_to_counter."""
    async with AsyncSessionLocal() as db:
        try:
            n, moves = await negotiation.make_offer(
                db, offer_id=_uuid(offer_id, "offer_id"), quantity=quantity, unit_price_cents=_cents(price_usd),
                message=message, buyer_name=buyer_name, buyer_kind="agent", token=negotiation_id)
        except ServiceError as exc:
            raise ToolError(str(exc)) from None
    return _negotiation(n, moves)


@mcp.tool()
async def respond_to_counter(negotiation_id: str, accept: bool, message: str = "") -> dict:
    """Accept the shop's latest counter (accept=true) or walk away (accept=false)."""
    async with AsyncSessionLocal() as db:
        try:
            n, moves = await negotiation.respond(db, negotiation_id, "accept" if accept else "walk_away", message)
        except ServiceError as exc:
            raise ToolError(str(exc)) from None
    return _negotiation(n, moves)


@mcp.tool()
async def place_order(pay_with: str, offer_id: str | None = None, quantity: int = 1,
                      negotiation_id: str | None = None, buyer_name: str = "A buyer agent",
                      buyer_email: str | None = None) -> dict:
    """Get an invoice and a one-time payment address. Either an agreed
    negotiation_id (its price and quantity) or an offer_id at its list price.
    pay_with is a coin and chain, e.g. "USDC on base" or "USDC on near"."""
    asset = await _coin(pay_with)
    async with AsyncSessionLocal() as db:
        try:
            if negotiation_id:
                invoice = await negotiation.invoice_agreed(db, negotiation_id, buyer_email=buyer_email,
                                                           buyer_name=buyer_name, ip_hash=None)
            elif offer_id:
                offer = await db.get(Offer, _uuid(offer_id, "offer_id"))
                shop = await db.get(Shop, offer.shop_id) if offer else None
                if shop is None:
                    raise ToolError("No such offer.")
                invoice = await invoices.issue_invoice(
                    db, shop, offer_id=offer.id, quantity=quantity, unit_price_cents=None, buyer_kind="agent",
                    buyer_email=buyer_email, buyer_name=buyer_name, ip_hash=None)
            else:
                raise ToolError("Pass an agreed negotiation_id, or an offer_id to buy at the list price.")
            invoice = await invoices.quote_payment(db, invoice, asset)
            return _invoice(await invoices.view(db, invoice))
        except ServiceError as exc:
            raise ToolError(str(exc)) from None


@mcp.tool()
async def invoice_status(invoice_token: str) -> dict:
    """Where an invoice stands: awaiting_payment, paid, delivered, expired or
    refunded, with what was delivered once it's paid."""
    async with AsyncSessionLocal() as db:
        try:
            invoice = await invoices.invoice_by_token(db, invoice_token)
            await invoices.check_invoice(db, invoice)
            return _invoice(await invoices.view(db, invoice))
        except ServiceError as exc:
            raise ToolError(str(exc)) from None


def build_app():
    """The /mcp routes and the session manager that must run for them. A new
    pair per app instance: a session manager can only be started once.

    Public over the internet, so the DNS-rebinding guard (for servers on
    localhost) is off; stateless JSON keeps every call independent."""
    app = mcp.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, json_response=True,
                                  transport_security=TransportSecuritySettings(
                                      enable_dns_rebinding_protection=False))
    return app.routes, mcp.session_manager
