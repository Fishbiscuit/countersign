from datetime import timedelta

import pytest

from countersign.policy import DEFAULT_MANDATE
from countersign.store import Store, fingerprint, iso, now, payment_key


def make_intent(store, agent_id, status="held", expires=None, currency="USD", reference="T-1"):
    intent = store.create_intent(
        agent_id=agent_id,
        session_id="s1",
        action="refund",
        amount="10.00",
        currency=currency,
        target="CAP",
        reference=reference,
        fingerprint="fp",
        request_id="cs-fp",
        backend="simulated",
    )
    return store.update_intent(intent.id, status=status, hold_expires_at=expires)


def test_two_agents_share_a_payment_key_but_keep_their_own_retries():
    move = ("refund", "CAP", "7.00", "USD", "T-1")
    assert payment_key(*move) == payment_key("refund", " cap ", "7.00", "USD", " t-1 ")
    assert payment_key(*move) != payment_key("refund", "CAP", "8.00", "USD", "T-1")
    assert fingerprint("agent-a", *move) != fingerprint("agent-b", *move)


def test_a_reference_finds_moves_by_any_agent_at_any_age(tmp_path):
    store = Store(tmp_path / "cs.db")
    paid = make_intent(store, "agent-a", status="executed")
    store.update_intent(paid.id, created_at=iso(now() - timedelta(days=30)))
    held = make_intent(store, "agent-b", status="held")
    make_intent(store, "agent-c", status="denied")
    make_intent(store, "agent-c", status="failed")
    make_intent(store, "agent-c", status="expired")
    make_intent(store, "agent-a", status="executed", reference="T-2")
    found = store.moves_under_reference("refund", "cap", "t-1")
    assert {m.id for m in found} == {paid.id, held.id}


def test_a_possible_duplicate_counts_other_agents_but_not_the_same_reference(tmp_path):
    store = Store(tmp_path / "cs.db")
    make_intent(store, "agent-a", status="executed", reference="T-1")
    since = now() - timedelta(minutes=60)
    assert store.moves_to_target("refund", "CAP", "T-2", since) == 1
    assert store.moves_to_target("refund", "CAP", "T-1", since) == 0


def test_agent_key_is_hashed_and_resolves(tmp_path):
    store = Store(tmp_path / "cs.db")
    agent, key = store.create_agent("Claude", "claude-code", DEFAULT_MANDATE)
    assert "key_hash" not in agent
    assert store.agent_by_key(key)["id"] == agent["id"]
    assert store.agent_by_key(key + "x") is None
    store.set_agent_active(agent["id"], False)
    assert store.agent_by_key(key) is None


def test_summary_never_adds_currencies_together(tmp_path):
    store = Store(tmp_path / "cs.db")
    for currency in ("USD", "USD", "SGD"):
        make_intent(store, "agt", status="executed", currency=currency)
    executed = store.summary(now() - timedelta(hours=1))["by_status"]["executed"]
    assert executed == {"count": 3, "totals": {"USD": 20.0, "SGD": 10.0}}


def test_a_hold_can_be_decided_once(tmp_path):
    store = Store(tmp_path / "cs.db")
    intent = make_intent(store, "agt")
    assert store.decide(intent.id, True, "human").status == "approved"
    assert store.decide(intent.id, False, "human") is None
    assert store.get_intent(intent.id).status == "approved"


def test_expired_hold_can_still_be_approved(tmp_path):
    store = Store(tmp_path / "cs.db")
    intent = make_intent(store, "agt", expires=iso(now() - timedelta(seconds=1)))
    assert store.expire_due_holds() == [intent.id]
    assert store.decide(intent.id, True, "human").status == "approved"


def test_executed_moves_cannot_be_decided(tmp_path):
    store = Store(tmp_path / "cs.db")
    intent = make_intent(store, "agt", status="executed")
    assert store.decide(intent.id, False, "human") is None


@pytest.mark.parametrize("status", ["executed", "denied", "approved", "expired"])
def test_a_retry_finds_its_intent_however_old(tmp_path, status):
    store = Store(tmp_path / "cs.db")
    intent = make_intent(store, "agt", status=status)
    with store._tx() as db:
        db.execute("UPDATE intents SET created_at = ? WHERE id = ?", (iso(now() - timedelta(days=30)), intent.id))
    assert store.find_by_fingerprint("fp").id == intent.id


@pytest.mark.parametrize("status", ["executed", "denied", "approved"])
def test_a_decision_outranks_a_later_undecided_attempt(tmp_path, status):
    store = Store(tmp_path / "cs.db")
    decided = make_intent(store, "agt", status=status)
    make_intent(store, "agt", status="expired")
    assert store.find_by_fingerprint("fp").id == decided.id


def test_events_are_ordered(tmp_path):
    store = Store(tmp_path / "cs.db")
    start = store.last_event_id()
    make_intent(store, "agt")
    kinds = [e["kind"] for e in store.events_after(start)]
    assert kinds[0] == "intent_created"
