"""Fill a group order with scripted buyer agents, to watch the market move
through its tiers (docs/RULES.md, "Simulation").

The buyers talk to the real MCP endpoint over HTTP, as any outside agent
would. They make no LLM calls and pay nothing; each is named "Sim buyer N"
so it's never mistaken for real demand.

    uv run python scripts/simulate_market.py                    # local dev (http://localhost:5180)
    uv run python scripts/simulate_market.py --url https://shops.thalace.com --buyers 12
    uv run python scripts/simulate_market.py --offer <offer id> --hours 0.25

Without --offer, it joins the open group order with the fewest units to go to
its next tier, or opens one on the first offer that takes group orders.
"""

import argparse
import json
import random
import sys
import urllib.request

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def call(url: str, tool: str, **args) -> dict | list:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": tool, "arguments": args}}).encode()
    request = urllib.request.Request(f"{url.rstrip('/')}/mcp", data=body, headers=HEADERS, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.load(response)["result"]
    if result.get("isError"):
        raise RuntimeError(result["content"][0]["text"])
    structured = result.get("structuredContent")
    if structured is not None:
        return structured["result"] if set(structured) == {"result"} else structured
    return json.loads(result["content"][0]["text"])


def usd(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def progress(group: dict) -> str:
    line = f"{group['committed_quantity']} committed at {usd(group['unit_price_cents'])} each"
    nxt = group.get("next_tier")
    if nxt:
        line += f"; {nxt['min_quantity'] - group['committed_quantity']} more for {usd(nxt['unit_price_cents'])}"
    return line + " (best tier reached)" if not nxt else line


def find_or_open(url: str, offer_id: str | None, hours: float) -> str:
    groups = call(url, "list_group_orders")
    if offer_id:
        groups = [g for g in groups if g["offer_id"] == offer_id]
    if groups:
        def to_go(g):
            nxt = g.get("next_tier")
            return nxt["min_quantity"] - g["committed_quantity"] if nxt else 10**6
        group = min(groups, key=to_go)
        print(f"Joining the open group order on {group['offer_title']} ({group['shop_name']}): {progress(group)}")
        return group["group_order_id"]
    if not offer_id:
        sys.exit("No open group order, and no --offer to open one on. Turn group buying on for an offer first.")
    opened = call(url, "open_group_order", offer_id=offer_id, quantity=1, hours=hours, buyer_name="Sim buyer 1")
    print(f"Sim buyer 1 opened a group order on {opened['offer_title']}: {progress(opened)}")
    return opened["group_order_id"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://localhost:5180")
    parser.add_argument("--buyers", type=int, default=8)
    parser.add_argument("--offer", help="the offer to open a group order on, if none is open")
    parser.add_argument("--hours", type=float, default=0.5, help="deadline for a group order it opens")
    parser.add_argument("--seed", type=int, default=7, help="the same seed gives the same buyers")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    group_id = find_or_open(args.url, args.offer, args.hours)
    for n in range(2, args.buyers + 2):
        # A scripted strategy: small buyers mostly, the odd bulk one.
        quantity = rng.choice([1, 1, 2, 2, 3, 5])
        try:
            joined = call(args.url, "join_group_order", group_order_id=group_id, quantity=quantity,
                          buyer_name=f"Sim buyer {n}")
        except RuntimeError as exc:
            print(f"Sim buyer {n} couldn't join: {exc}")
            break
        print(f"Sim buyer {n} joined with {quantity}: {progress(joined)}")
    print("\nAt the deadline the price locks at the tier reached and each member gets their own invoice. "
          "Simulated buyers never pay.")


if __name__ == "__main__":
    main()
