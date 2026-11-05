from collections.abc import Iterator

from app.negotiation import negotiate_events
from app.planner import plan_trip


def negotiate_plan_events(profile: dict) -> Iterator[dict]:
    """Plan a trip, then negotiate every item, yielding events as they happen.

    Event types: plan, round, item_done, done.
    """
    plan = plan_trip(profile)
    yield {"type": "plan", "plan": plan}

    lines = []
    running_saved = 0

    for index, item in enumerate(plan["items"]):
        result = None
        # The planned price is the list price for these dates, and also our walk-away price:
        # we never pay more than the plan said.
        for event in negotiate_events(
            item["item_id"], [], item["unit_price"], list_override=item["unit_price"]
        ):
            if event["type"] == "round":
                yield {**event, "item_index": index}
            else:
                result = event["result"]

        deal = result["deal"]
        final_unit = deal["price"] if deal else item["unit_price"]
        line = {
            **item,
            "final_unit_price": final_unit,
            "final_total": final_unit * item["quantity"],
            "saved": (item["unit_price"] - final_unit) * item["quantity"],
            "perks": deal["perks"] if deal else [],
            "rounds": result["rounds"],
        }
        lines.append(line)
        running_saved += line["saved"]
        yield {
            "type": "item_done",
            "item_index": index,
            "item_name": line["name"],
            "line": line,
            "running_saved": running_saved,
        }

    list_total = plan["list_total"]
    final_total = sum(line["final_total"] for line in lines)
    saved = list_total - final_total

    yield {
        "type": "done",
        "trip": {
            "profile": plan["profile"],
            "stay": plan["stay"],
            "items": lines,
            "list_total": list_total,
            "final_total": final_total,
            "saved": saved,
            "savings_pct": round(100 * saved / list_total, 1) if list_total else 0,
            "budget": plan["budget"],
            "within_budget": final_total <= plan["budget"],
            "notes": plan["notes"],
        },
    }


def negotiate_plan(profile: dict) -> dict:
    """Run the whole trip to the end and return only the final result."""
    trip = None
    for event in negotiate_plan_events(profile):
        if event["type"] == "done":
            trip = event["trip"]
    return trip