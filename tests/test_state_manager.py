"""Unit tests for the authoritative state manager."""
import json

import pytest

from app.game.models import DIE_TYPES
from app.game.state_manager import StateError, StateManager


@pytest.fixture
def sm():
    return StateManager()


def test_initial_dice(sm):
    state = sm.get_state()
    assert len(state.dice) == 12
    for owner in (1, 2):
        for die_type in DIE_TYPES:
            die = state.dice[f"p{owner}-{die_type}"]
            assert die.owner == owner
            assert die.type == die_type
            assert die.location == f"p{owner}_fixer"
            assert die.last_roll is None
    assert state.latest_cards == {"1": None, "2": None}
    assert state.locations == ["p1_fixer", "p1_gig", "p2_fixer", "p2_gig"]
    for player in ("1", "2"):
        assert len(state.legends[player]) == 3
        assert all(not slot.revealed and slot.card_id is None for slot in state.legends[player])
    assert state.match.player1_cred == 0


def test_move_die(sm):
    sm.move_die("p1-d8", "p2_gig")
    state = sm.get_state()
    assert state.dice["p1-d8"].location == "p2_gig"
    # Original ownership never changes when moved into opponent territory.
    assert state.dice["p1-d8"].owner == 1


def test_move_opponent_owned_die(sm):
    sm.move_die("p2-d20", "p1_fixer")
    state = sm.get_state()
    assert state.dice["p2-d20"].location == "p1_fixer"
    assert state.dice["p2-d20"].owner == 2


def test_move_invalid_die(sm):
    with pytest.raises(StateError):
        sm.move_die("p3-d8", "p1_gig")


def test_move_invalid_location(sm):
    with pytest.raises(StateError):
        sm.move_die("p1-d8", "the_moon")


def test_move_noop_rejected(sm):
    with pytest.raises(StateError):
        sm.move_die("p1-d8", "p1_fixer")


def test_roll_valid(sm):
    sm.roll_die("p1-d8", 6)
    assert sm.get_state().dice["p1-d8"].last_roll == 6


@pytest.mark.parametrize("die_type,sides", DIE_TYPES.items())
def test_roll_limits(sm, die_type, sides):
    die_id = f"p1-{die_type}"
    sm.roll_die(die_id, 1)
    sm.roll_die(die_id, sides)
    with pytest.raises(StateError):
        sm.roll_die(die_id, 0)
    with pytest.raises(StateError):
        sm.roll_die(die_id, sides + 1)


def test_d4_rejects_seven(sm):
    with pytest.raises(StateError):
        sm.roll_die("p1-d4", 7)


def test_undo_move(sm):
    sm.move_die("p1-d8", "p2_gig")
    sm.undo()
    assert sm.get_state().dice["p1-d8"].location == "p1_fixer"


def test_undo_roll(sm):
    sm.roll_die("p1-d8", 6)
    sm.undo()
    assert sm.get_state().dice["p1-d8"].last_roll is None


def test_redo(sm):
    sm.move_die("p1-d8", "p2_gig")
    sm.undo()
    sm.redo()
    assert sm.get_state().dice["p1-d8"].location == "p2_gig"


def test_redo_cleared_by_new_action(sm):
    sm.move_die("p1-d8", "p2_gig")
    sm.undo()
    sm.roll_die("p1-d6", 3)
    with pytest.raises(StateError):
        sm.redo()


def test_undo_empty(sm):
    with pytest.raises(StateError):
        sm.undo()
    with pytest.raises(StateError):
        sm.redo()


def test_card_override(sm):
    sm.set_latest_card(1, "card-001", "Rebecca", "Having a Moment", "/img.svg", "manual")
    lc = sm.get_state().latest_cards["1"]
    assert lc.card_id == "card-001"
    assert lc.source == "manual"
    assert lc.player == 1
    assert sm.get_state().latest_cards["2"] is None


def test_latest_cards_per_player(sm):
    sm.set_latest_card(1, "card-001", "Rebecca")
    sm.set_latest_card(2, "card-002", "Street Samurai", source="vision", confidence=0.95)
    state = sm.get_state()
    assert state.latest_cards["1"].card_id == "card-001"
    assert state.latest_cards["2"].card_id == "card-002"


def test_card_override_undo(sm):
    sm.set_latest_card(1, "card-001", "Rebecca", source="manual")
    sm.set_latest_card(1, "card-002", "Street Samurai", source="vision", confidence=0.95)
    sm.undo()
    assert sm.get_state().latest_cards["1"].card_id == "card-001"
    sm.undo()
    assert sm.get_state().latest_cards["1"] is None


def test_card_invalid_source(sm):
    with pytest.raises(StateError):
        sm.set_latest_card(1, "card-001", "Rebecca", source="guess")


def test_reset(sm):
    sm.set_player_names("Alice", "Bob")
    sm.move_die("p1-d8", "p2_gig")
    sm.roll_die("p1-d8", 6)
    sm.set_latest_card(1, "card-001", "Rebecca")
    sm.set_legend(1, 0, "card-002", name="Street Samurai")
    sm.set_street_cred(1, 7)
    sm.reset_match()
    state = sm.get_state()
    assert state.dice["p1-d8"].location == "p1_fixer"
    assert state.dice["p1-d8"].last_roll is None
    assert state.latest_cards == {"1": None, "2": None}
    assert state.legends["1"][0].card_id is None
    assert state.match.player1_cred == 0
    # Player names survive a reset.
    assert state.match.player1_name == "Alice"
    assert state.match.player2_name == "Bob"


def test_legend_set_reveal_clear(sm):
    sm.set_legend(1, 0, "card-002", name="Street Samurai", image="/img.svg")
    legend = sm.get_state().legends["1"][0]
    assert legend.card_id == "card-002" and legend.revealed is False
    sm.reveal_legend(1, 0, True)
    assert sm.get_state().legends["1"][0].revealed is True
    sm.set_legend(1, 0, None)
    legend = sm.get_state().legends["1"][0]
    assert legend.card_id is None and legend.revealed is False


def test_legend_reveal_without_card_rejected(sm):
    with pytest.raises(StateError):
        sm.reveal_legend(1, 1, True)


def test_legend_invalid_slot(sm):
    with pytest.raises(StateError):
        sm.set_legend(1, 3, "card-001")
    with pytest.raises(StateError):
        sm.set_legend(3, 0, "card-001")


def test_legend_undo(sm):
    sm.set_legend(2, 1, "card-003", name="Netrunner")
    sm.reveal_legend(2, 1, True)
    sm.undo()
    assert sm.get_state().legends["2"][1].revealed is False
    sm.undo()
    assert sm.get_state().legends["2"][1].card_id is None


def test_street_cred(sm):
    sm.set_street_cred(1, 7)
    assert sm.get_state().match.player1_cred == 7
    sm.undo()
    assert sm.get_state().match.player1_cred == 0
    with pytest.raises(StateError):
        sm.set_street_cred(1, -1)
    with pytest.raises(StateError):
        sm.set_street_cred(1, 100)


def test_reset_is_undoable(sm):
    sm.move_die("p1-d8", "p2_gig")
    sm.reset_match()
    sm.undo()
    assert sm.get_state().dice["p1-d8"].location == "p2_gig"


def test_swap_sides_keeps_ownership(sm):
    sm.move_die("p1-d8", "p2_gig")
    sm.swap_sides()
    state = sm.get_state()
    assert state.match.sides_swapped is True
    assert state.dice["p1-d8"].owner == 1
    assert state.dice["p1-d8"].location == "p2_gig"
    sm.swap_sides()
    assert sm.get_state().match.sides_swapped is False


def test_events_recorded(sm):
    sm.roll_die("p1-d8", 6)
    events = sm.get_state().recent_events
    assert events[-1].type == "die_rolled"
    assert "P1 d8 → 6" in events[-1].description


def test_event_cap(sm):
    for _ in range(60):
        sm.roll_die("p1-d20", 10)
        sm.roll_die("p1-d20", 11)
    assert len(sm.get_state().recent_events) == StateManager.MAX_EVENTS


def test_history_info(sm):
    info = sm.history_info()
    assert info["can_undo"] is False
    sm.roll_die("p1-d8", 6)
    info = sm.history_info()
    assert info["can_undo"] is True
    assert "d8" in info["undo_description"]


def test_state_serializes_to_json(sm):
    sm.roll_die("p1-d8", 6)
    sm.set_latest_card(1, "card-001", "Rebecca")
    payload = sm.get_state().model_dump()
    text = json.dumps(payload)
    restored = json.loads(text)
    assert restored["dice"]["p1-d8"]["last_roll"] == 6
    assert restored["latest_cards"]["1"]["card_id"] == "card-001"
    assert len(restored["legends"]["1"]) == 3


def test_street_cred_is_gig_total(sm):
    """Cred = sum of roll values of the dice in the player's gig area."""
    sm.roll_die("p1-d6", 4)
    assert sm.get_state().match.player1_cred == 0      # rolled but still in the fixer area
    sm.move_die("p1-d6", "p1_gig")
    assert sm.get_state().match.player1_cred == 4
    sm.move_die("p2-d20", "p1_gig")                    # captured opponent die, unrolled
    assert sm.get_state().match.player1_cred == 4
    sm.roll_die("p2-d20", 15)
    assert sm.get_state().match.player1_cred == 19
    assert sm.get_state().match.player2_cred == 0
    sm.move_die("p2-d20", "p2_gig")
    assert sm.get_state().match.player1_cred == 4 and sm.get_state().match.player2_cred == 15
    sm.undo()
    assert sm.get_state().match.player1_cred == 19


def test_street_cred_manual_adjustment_persists(sm):
    sm.roll_die("p1-d8", 6)
    sm.move_die("p1-d8", "p1_gig")
    sm.set_street_cred(1, 8)                           # operator bumps 6 -> 8
    assert sm.get_state().match.player1_cred == 8
    sm.roll_die("p1-d8", 2)                            # re-roll: 2 + adjustment 2
    assert sm.get_state().match.player1_cred == 4
    sm.move_die("p1-d8", "p1_fixer")
    assert sm.get_state().match.player1_cred == 2
    sm.reset_match()
    assert sm.get_state().match.player1_cred == 0


def test_swap_legends(sm):
    sm.set_legend(1, 0, "cb-v-streetkid", name="V", image="/v.webp")
    sm.reveal_legend(1, 0, True)
    sm.swap_legends(1, 0, 2)
    legends = sm.get_state().legends["1"]
    assert legends[0].card_id is None
    assert legends[2].card_id == "cb-v-streetkid" and legends[2].revealed is True
    sm.undo()
    assert sm.get_state().legends["1"][0].card_id == "cb-v-streetkid"
    with pytest.raises(StateError):
        sm.swap_legends(1, 1, 1)
    with pytest.raises(StateError):
        sm.swap_legends(1, 0, 3)
