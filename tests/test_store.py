from datetime import timedelta

import pytest

from countersign.policy import DEFAULT_MANDATE
from countersign.store import Store, iso, now


def make_intent(store, agent_id, status="held", expires=None):
    intent = store.create_intent(
        agent_id=agent_id,
        session_id="s1",
        action="refund",
        amount="10.00",
        currency="USD",
        target="CAP",
        reference="T-1",
        fingerprint="fp",
        request_id="cs-fp",
        backend="simulated",
    )
    return store.update_intent(intent.id, status=status, hold_expires_at=expires)


def test_agent_key_is_hashed_and_resolves(tmp_path):
    store = Store(tmp_path / "cs.db")
    agent, key = store.create_agent("Claude", "claude-code", DEFAULT_MANDATE)
    assert "key_hash" not in agent
    assert store.agent_by_key(key)["id"] == agent["id"]
    assert store.agent_by_key(key + "x") is None
    store.set_agent_active(agent["id"], False)
    assert store.agent_by_key(key) is None


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
