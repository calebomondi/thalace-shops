"""The shop agent's loop, with the model scripted: what its tools may and
may not do, the tool-call cap, and the conversation it keeps."""

import json
import uuid

import psycopg
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from agents.shop.graph import close_dangling_tool_calls, history_window
from agents.shop.tools import to_cents
from app.database.models import Shop
from app.services import shop_agent
from config import settings
from data_sources.web.firecrawl import Page, PageReadError


def call(name: str, **args) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"id": f"call-{uuid.uuid4().hex[:8]}", "name": name, "args": args}])


class Script:
    """Replies in order, recording what the agent was given each step."""

    def __init__(self, *replies: AIMessage):
        self.replies = list(replies)
        self.seen: list[tuple[list, list[str]]] = []

    def __call__(self, messages, tools):
        self.seen.append((list(messages), [t.name for t in tools]))
        return self.replies.pop(0) if self.replies else AIMessage(content="Done.")


async def _page(url: str) -> Page:
    return Page(url=url, title="Shanga Prints", markdown="We do CAD design and 3D printing in Nairobi.",
                truncated=False)


@pytest.fixture
async def db():
    engine = create_async_engine(settings.sqlalchemy_database_url, poolclass=NullPool)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def shop(db):
    shop = Shop(owner_id=uuid.uuid4(), slug="shanga-cad", name="Shanga CAD Studio",
                settlement_asset=settings.default_settlement_asset, daily_budget_usd=20)
    db.add(shop)
    await db.commit()
    return shop


def _offers(shop_id) -> list[tuple]:
    with psycopg.connect(settings.database_url) as conn:
        return conn.execute("SELECT title, status, price_cents, floor_cents, created_by FROM offers"
                            " WHERE shop_id = %s ORDER BY created_at", (shop_id,)).fetchall()


async def test_the_agent_reads_the_site_and_drafts_an_offer(db, shop):
    script = Script(
        call("read_website", url="https://prints.shangalabs.com"),
        call("draft_offer", title="CAD print-readiness review", description="We check your file prints well.",
             kind="service", price_usd="15", floor_usd="10", delivery="markdown",
             delivery_note="A written review within a day."),
        AIMessage(content="I drafted a review offer at $15 (lowest $10). Put it on sale when you're happy."),
    )
    turn = await shop_agent.run_turn(db, shop, shop.owner_id, "Draft an offer from my site",
                                     model_step=script, page_reader=_page)
    assert [m["role"] for m in turn] == ["user", "assistant"]
    assert turn[1]["actions"] == ["read_website", "draft_offer"]
    assert _offers(shop.id) == [("CAD print-readiness review", "draft", 1500, 1000, None)]
    # The page reached the model as data inside a tool result.
    tool_results = [m for m in script.seen[1][0] if isinstance(m, ToolMessage)]
    assert "CAD design" in tool_results[0].content


async def test_the_agent_cannot_change_an_offer_on_sale(db, shop):
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        offer_id = conn.execute(
            "INSERT INTO offers (id, shop_id, title, kind, price_cents, floor_cents, delivery, status)"
            " VALUES (%s, %s, 'Keychain', 'service', 500, 500, 'service', 'active') RETURNING id",
            (uuid.uuid4(), shop.id)).fetchone()[0]
    script = Script(call("update_draft_offer", offer_id=str(offer_id), title="Keychain", description="",
                         kind="service", price_usd="1", delivery="service"))
    await shop_agent.run_turn(db, shop, shop.owner_id, "Make the keychain $1", model_step=script, page_reader=_page)
    result = json.loads([m for m in script.seen[1][0] if isinstance(m, ToolMessage)][-1].content)
    assert result["ok"] is False and "only the owner" in result["error"]
    assert _offers(shop.id)[0][2] == 500


async def test_a_floor_above_the_price_is_refused_to_the_model(db, shop):
    script = Script(call("draft_offer", title="Engraving", description="", kind="service", price_usd="10",
                         floor_usd="12", delivery="service"))
    await shop_agent.run_turn(db, shop, shop.owner_id, "Draft engraving", model_step=script, page_reader=_page)
    result = json.loads([m for m in script.seen[1][0] if isinstance(m, ToolMessage)][-1].content)
    assert result["ok"] is False and _offers(shop.id) == []


async def test_a_page_that_cant_be_read_is_a_result_not_a_crash(db, shop):
    async def unreadable(url):
        raise PageReadError("That page couldn't be read (status 404).")
    script = Script(call("read_website", url="https://example.com/missing"))
    turn = await shop_agent.run_turn(db, shop, shop.owner_id, "Read it", model_step=script, page_reader=unreadable)
    assert turn[-1]["content"] == "Done."


async def test_past_the_tool_call_cap_the_agent_must_answer(db, shop, monkeypatch):
    monkeypatch.setattr(settings, "agent_max_tool_calls_per_turn", 2)
    script = Script(call("list_offers"), call("list_offers"), call("list_offers"))
    await shop_agent.run_turn(db, shop, shop.owner_id, "Loop", model_step=script, page_reader=_page)
    assert script.seen[2][1] == []
    assert any(isinstance(m, SystemMessage) and "tool calls" in m.content for m in script.seen[2][0])


async def test_the_next_turn_remembers_the_last(db, shop):
    await shop_agent.run_turn(db, shop, shop.owner_id, "Hello", model_step=Script(AIMessage(content="Hi!")),
                              page_reader=_page)
    second = Script(AIMessage(content="You said hello."))
    await shop_agent.run_turn(db, shop, shop.owner_id, "What did I say?", model_step=second, page_reader=_page)
    contents = [m.content for m in second.seen[0][0]]
    assert "Hello" in contents and "Hi!" in contents
    assert [m["content"] for m in await shop_agent.conversation(db, shop)] == [
        "Hello", "Hi!", "What did I say?", "You said hello."]


def test_prices_are_read_as_dollars_and_cents():
    assert (to_cents("15", "p"), to_cents("$1,250.50", "p"), to_cents(9.99, "p")) == (1500, 125050, 999)
    with pytest.raises(ValueError):
        to_cents("0", "p")
    with pytest.raises(ValueError):
        to_cents("ten", "p")


def test_an_unanswered_tool_call_is_closed_before_it_is_replayed():
    dangling = AIMessage(content="", tool_calls=[{"id": "c1", "name": "list_offers", "args": {}}])
    closed = close_dangling_tool_calls([dangling])
    assert isinstance(closed[1], ToolMessage) and closed[1].tool_call_id == "c1"


def test_the_history_window_keeps_the_current_turn_whole():
    old = [HumanMessage(content="x" * 4000), AIMessage(content="y" * 4000)]
    now = [HumanMessage(content="latest"), AIMessage(content="z" * 8000)]
    assert history_window(old + now, budget_tokens=100) == now
