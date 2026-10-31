"""Which untrusted reads a hold keeps, and which one the move is about."""

import json

from countersign.gateway_hook import sources_for_hold


def ticket(ticket_id: str) -> dict:
    return {"tool": "shop_read_ticket", "excerpt": json.dumps({"id": ticket_id, "body": f"Body of {ticket_id}"}), "at": ticket_id}


def inbox(*ticket_ids: str) -> dict:
    """How a list tool's result is recorded: its items' text blocks, joined by newlines."""
    excerpt = "\n".join(json.dumps({"id": ticket_id}, indent=2) for ticket_id in ticket_ids)
    return {"tool": "shop_list_tickets", "excerpt": excerpt, "at": "list"}


def about(sources: list[dict]) -> list[str]:
    return [source["at"] for source in sources if source["about_move"]]


def test_the_ticket_the_move_is_about_comes_first_even_if_it_was_read_first():
    sources = sources_for_hold([ticket("T-1002"), ticket("T-1003"), ticket("T-1004")], "T-1002")

    assert [source["at"] for source in sources] == ["T-1002", "T-1003", "T-1004"]
    assert about(sources) == ["T-1002"]


def test_a_list_of_every_ticket_is_not_about_this_move():
    sources = sources_for_hold([inbox("T-1001", "T-1002"), ticket("T-1002")], "T-1002")

    assert about(sources) == ["T-1002"]
    assert sources[0]["at"] == "T-1002"


def test_a_structured_list_is_not_about_this_move_either():
    listing = {"tool": "shop_list_tickets", "excerpt": json.dumps({"result": [{"id": "T-1002"}]}), "at": "list"}

    assert about(sources_for_hold([listing], "T-1002")) == []


def test_a_ticket_that_only_mentions_the_reference_is_not_about_this_move():
    mention = {"tool": "shop_read_ticket", "excerpt": json.dumps({"id": "T-1003", "body": "Same as T-1002"}), "at": "T-1003"}

    assert about(sources_for_hold([mention], "T-1002")) == []


def test_matching_ignores_case_and_works_on_plain_text():
    plain = {"tool": "web_fetch", "excerpt": "Case t-1002: the bowl was late.", "at": "plain"}
    longer = {"tool": "web_fetch", "excerpt": "Case T-10021: something else.", "at": "longer"}

    assert about(sources_for_hold([plain, longer], "T-1002")) == ["plain"]


def test_with_no_match_the_sources_stay_in_the_order_they_were_read():
    sources = sources_for_hold([ticket("T-1"), ticket("T-2")], "Order 9")

    assert [source["at"] for source in sources] == ["T-1", "T-2"]
    assert about(sources) == []


def test_the_move_s_ticket_survives_the_limit_along_with_the_latest_reads():
    reads = [ticket(f"T-{n}") for n in range(1, 9)]

    sources = sources_for_hold(reads, "T-1")

    assert [source["at"] for source in sources] == ["T-1", "T-5", "T-6", "T-7", "T-8"]


def test_stored_excerpts_are_cut_to_length():
    source = {"tool": "web_fetch", "excerpt": "x" * 2000, "at": "long"}

    assert len(sources_for_hold([source], "T-1")[0]["excerpt"]) == 800
