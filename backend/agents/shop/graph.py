"""The shop agent: one ReAct loop per shop.

    agent --(tool calls)--> tools --> agent ... --(answer)--> END

State is only the conversation. What the agent knows about the shop reaches
the model two ways: the system prompt on every step, and the tools.

Bounds per owner turn: at most `agent_max_tool_calls_per_turn` tool calls,
after which the model must answer with what it has, and at most
`agent_history_token_budget` tokens of conversation re-sent each step. The
backend caps the turn's wall clock.
"""

import asyncio
from collections.abc import Callable, Sequence
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from agents.llm.main import invoke_with_tools
from agents.shop.prompts import system_prompt
from agents.shop.store import ShopStore
from agents.shop.tools import PageReader, build_tools
from config import Settings, get_settings

# The model step, injectable so tests can script it: (messages, tools) -> AIMessage.
ModelStep = Callable[[Sequence[AnyMessage], Sequence[BaseTool]], AnyMessage]

_OUT_OF_TOOL_CALLS = (
    "You have used this turn's tool calls. Answer the owner now with what you have, "
    "and say what you would look into next."
)
_INTERRUPTED = '{"ok": false, "summary": "Interrupted before it finished.", "error": "interrupted"}'
# Rough characters per token, for the history budget; precise enough to keep
# well inside every model's window.
_CHARS_PER_TOKEN = 4


class ShopAgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


def _default_step(messages: Sequence[AnyMessage], tools: Sequence[BaseTool]) -> AnyMessage:
    return invoke_with_tools(messages, tools, log_label="shop:step")


def _turn_start(messages: Sequence[AnyMessage]) -> int:
    """Index of the owner's latest message: where this turn began."""
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            return i
    return 0


def tool_calls_this_turn(messages: Sequence[AnyMessage]) -> int:
    return sum(isinstance(m, ToolMessage) for m in messages[_turn_start(messages):])


def close_dangling_tool_calls(messages: Sequence[AnyMessage]) -> list[AnyMessage]:
    """Answer any tool call that never got a result, so the model is never sent
    a call without its answer (providers reject that). It happens when a turn
    times out or the server restarts between the call and its result."""
    answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    out: list[AnyMessage] = []
    for message in messages:
        out.append(message)
        for tool_call in getattr(message, "tool_calls", None) or []:
            if tool_call["id"] not in answered:
                out.append(ToolMessage(content=_INTERRUPTED, tool_call_id=tool_call["id"]))
    return out


def history_window(messages: Sequence[AnyMessage], budget_tokens: int) -> list[AnyMessage]:
    """The most recent messages that fit the budget, starting on an owner
    message so a tool result is never sent without the call that made it. The
    current turn is always kept whole, even over budget."""
    turn = _turn_start(messages)
    used = sum(len(str(m.content)) for m in messages[turn:]) // _CHARS_PER_TOKEN
    start = turn
    for i in range(turn - 1, -1, -1):
        used += len(str(messages[i].content)) // _CHARS_PER_TOKEN
        if used > budget_tokens:
            break
        if isinstance(messages[i], HumanMessage):
            start = i
    return list(messages[start:])


def build_shop_graph(store: ShopStore, read_page: PageReader, *, settings: Settings | None = None,
                     model_step: ModelStep = _default_step):
    """Compile the agent for one shop; `store` scopes every tool to it."""
    settings = settings or get_settings()
    tools = build_tools(store, read_page)

    async def agent(state: ShopAgentState) -> dict:
        messages = state["messages"]
        prompt: list[AnyMessage] = [SystemMessage(content=system_prompt(await store.shop()))]
        prompt += close_dangling_tool_calls(history_window(messages, settings.agent_history_token_budget))
        allowed: Sequence[BaseTool] = tools
        if tool_calls_this_turn(messages) >= settings.agent_max_tool_calls_per_turn:
            prompt.append(SystemMessage(content=_OUT_OF_TOOL_CALLS))
            allowed = []
        # The provider ladder is synchronous and sleeps on throttles: off the event loop.
        reply = await asyncio.to_thread(model_step, prompt, allowed)
        return {"messages": [reply]}

    def route(state: ShopAgentState) -> Literal["tools", "__end__"]:
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else END

    builder = StateGraph(ShopAgentState)
    builder.add_node("agent", agent)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", route, {"tools": "tools", END: END})
    builder.add_edge("tools", "agent")
    return builder.compile()
