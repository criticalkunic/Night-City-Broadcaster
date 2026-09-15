"""Authoritative match state with undo/redo.

All mutation happens through StateManager methods under a lock. Each mutation
pushes a deep snapshot onto the undo stack, so undo/redo is uniform across die
moves, rolls, card overrides, and match controls. State is small, so snapshot
undo is the simple, reliable choice.
"""
import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from app.game.models import (
    DEFAULT_LOCATIONS,
    DIE_TYPES,
    LOCATION_LABELS,
    Die,
    GameEvent,
    GameState,
    LatestCard,
    LegendSlot,
    MatchInfo,
)

LEGEND_SLOTS = 3

log = logging.getLogger("app.state")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateError(ValueError):
    """Invalid state mutation requested (bad die, value out of range, ...)."""


class StateManager:
    MAX_HISTORY = 100
    MAX_EVENTS = 50

    def __init__(self, locations: Optional[list[str]] = None, require_fresh_play: bool = False):
        self.require_fresh_play = False  # Legacy constructor option; tracking is always enabled.
        self._lock = threading.Lock()
        self.locations = list(locations or DEFAULT_LOCATIONS)
        self._state = self._initial_state()
        self._undo_stack: list[tuple[str, GameState]] = []
        self._redo_stack: list[tuple[str, GameState]] = []

    # ------------------------------------------------------------- helpers

    def _initial_state(self, match: Optional[MatchInfo] = None) -> GameState:
        dice: dict[str, Die] = {}
        for owner in (1, 2):
            for die_type in DIE_TYPES:
                die_id = f"p{owner}-{die_type}"
                dice[die_id] = Die(
                    id=die_id,
                    owner=owner,
                    type=die_type,
                    location=f"p{owner}_fixer",
                )
        return GameState(
            awaiting_first_play=self.require_fresh_play,
            match=match or MatchInfo(),
            latest_cards={"1": None, "2": None},
            legends={
                "1": [LegendSlot() for _ in range(LEGEND_SLOTS)],
                "2": [LegendSlot() for _ in range(LEGEND_SLOTS)],
            },
            dice=dice,
            recent_events=[],
            locations=list(self.locations),
        )

    def _push_undo(self, description: str) -> None:
        self._undo_stack.append((description, self._state.model_copy(deep=True)))
        if len(self._undo_stack) > self.MAX_HISTORY:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _record_event(self, event_type: str, description: str, data: dict) -> GameEvent:
        event = GameEvent(type=event_type, description=description, timestamp=_now(), data=data)
        self._state.recent_events.append(event)
        if len(self._state.recent_events) > self.MAX_EVENTS:
            self._state.recent_events.pop(0)
        return event

    def _location_label(self, location: str) -> str:
        return LOCATION_LABELS.get(location, location)

    # -------------------------------------------------------------- reads

    def get_state(self) -> GameState:
        with self._lock:
            return self._state.model_copy(deep=True)

    def history_info(self) -> dict:
        with self._lock:
            return {
                "can_undo_card": bool(self._state.card_play_history),
                "card_undo_count": len(self._state.card_play_history),
                "can_undo": bool(self._undo_stack),
                "can_redo": bool(self._redo_stack),
                "undo_description": self._undo_stack[-1][0] if self._undo_stack else None,
                "redo_description": self._redo_stack[-1][0] if self._redo_stack else None,
            }

    # ---------------------------------------------------------------- cred

    def gig_total(self, player: int) -> int:
        """Combined value of the gigs a player controls: the roll values of all
        dice currently in that player's gig area (unrolled dice count 0)."""
        return sum(
            die.last_roll or 0
            for die in self._state.dice.values()
            if die.location == f"p{player}_gig"
        )

    def _recompute_cred(self) -> None:
        """Street cred is derived: gig total + operator adjustment, clamped 0-99."""
        for player in (1, 2):
            adjust = getattr(self._state.match, f"player{player}_cred_adjust")
            value = max(0, min(99, self.gig_total(player) + adjust))
            setattr(self._state.match, f"player{player}_cred", value)

    # ---------------------------------------------------------------- dice

    def move_die(self, die_id: str, location: str) -> GameEvent:
        with self._lock:
            die = self._state.dice.get(die_id)
            if die is None:
                raise StateError(f"Unknown die: {die_id}")
            if location not in self._state.locations:
                raise StateError(f"Unknown location: {location}")
            if die.location == location:
                raise StateError(f"{die_id} is already in {location}")
            description = f"P{die.owner} {die.type}: {self._location_label(die.location)} → {self._location_label(location)}"
            self._push_undo(description)
            previous = die.location
            die.location = location
            self._recompute_cred()
            event = self._record_event(
                "die_moved",
                description,
                {"die_id": die_id, "from": previous, "to": location},
            )
            log.info("DIE_MOVED die=%s from=%s to=%s", die_id, previous, location)
            return event

    def roll_die(self, die_id: str, value: int) -> GameEvent:
        with self._lock:
            die = self._state.dice.get(die_id)
            if die is None:
                raise StateError(f"Unknown die: {die_id}")
            sides = DIE_TYPES[die.type]
            if not isinstance(value, int) or not 1 <= value <= sides:
                raise StateError(f"{die.type} roll must be 1-{sides}, got {value}")
            description = f"P{die.owner} {die.type} → {value}"
            self._push_undo(description)
            die.last_roll = value
            self._recompute_cred()
            event = self._record_event(
                "die_rolled",
                description,
                {"die_id": die_id, "result": value},
            )
            log.info("DIE_ROLLED die=%s result=%s", die_id, value)
            return event

    # ---------------------------------------------------------------- card

    def observe_empty_play_region(self) -> bool:
        """Arm automatic play detection only after the presentation area clears."""
        with self._lock:
            changed = self._state.awaiting_first_play
            self._state.awaiting_first_play = False
            return changed

    def set_latest_card(
        self,
        player: int,
        card_id: str,
        name: str,
        subtitle: str = "",
        image: str = "",
        source: str = "manual",
        confidence: Optional[float] = None,
    ) -> GameEvent:
        with self._lock:
            if player not in (1, 2):
                raise StateError(f"Invalid player: {player}")
            if source not in ("manual", "vision"):
                raise StateError(f"Invalid card source: {source}")
            self._state.awaiting_first_play = False
            description = f"P{player} latest card: {name} ({source})"
            self._push_undo(description)
            if player == 1:
                self._state.card_play_history.append(self._state.last_played_card)
                self._state.card_play_history = self._state.card_play_history[-100:]
            self._state.latest_cards[str(player)] = LatestCard(
                player=player,
                card_id=card_id,
                name=name,
                subtitle=subtitle,
                image=image,
                source=source,
                confidence=confidence,
                timestamp=_now(),
            )
            if player == 1:
                self._state.last_played_card = self._state.latest_cards["1"].model_copy(deep=True)
            event_type = "card_overridden" if source == "manual" else "card_recognized"
            event = self._record_event(
                event_type,
                description,
                {"player": player, "card_id": card_id, "source": source, "confidence": confidence},
            )
            log.info(
                "LATEST_CARD player=%s card=%s source=%s confidence=%s",
                player, card_id, source, confidence,
            )
            return event

    def undo_card_play(self) -> GameEvent:
        with self._lock:
            if not self._state.card_play_history:
                raise StateError("No earlier card play")
            self._push_undo("Card play stepped back")
            previous = self._state.card_play_history.pop()
            self._state.latest_cards["1"] = previous.model_copy(deep=True) if previous else None
            self._state.last_played_card = previous.model_copy(deep=True) if previous else None
            return self._record_event("card_play_undone", "Stepped back one card play", {})

    def clear_latest_card(self) -> GameEvent:
        with self._lock:
            self._push_undo("Latest card cleared")
            self._state.latest_cards["1"] = None
            return self._record_event("card_cleared", "Latest card cleared", {})

    def remove_detected_card(self, player: int) -> Optional[GameEvent]:
        """Clear an absent card once, including a manually corrected identity."""
        with self._lock:
            if player not in (1, 2):
                raise StateError(f"Invalid player: {player}")
            card = self._state.latest_cards[str(player)]
            if card is None:
                return None
            description = f"P{player} card removed: {card.name}"
            self._push_undo(description)
            self._state.latest_cards[str(player)] = None
            return self._record_event("card_removed", description,
                                      {"player": player, "card_id": card.card_id})

    def set_gig(self, die_id: str, value: int | None) -> GameEvent:
        """Add/update a controlled gig, or return it to its owner's reserve."""
        with self._lock:
            die = self._state.dice.get(die_id)
            if die is None:
                raise StateError(f"Unknown die: {die_id}")
            if value is not None and not 1 <= value <= DIE_TYPES[die.type]:
                raise StateError(f"{die.type} value must be 1-{DIE_TYPES[die.type]}")
            self._push_undo("Gig updated")
            die.location = "p1_gig" if value is not None else f"p{die.owner}_fixer"
            die.last_roll = value
            self._recompute_cred()
            return self._record_event("gig_updated", "Gig updated", {"die_id": die_id})

    # ------------------------------------------------------------- legends

    def _legend_slot(self, player: int, slot: int) -> LegendSlot:
        if player not in (1, 2):
            raise StateError(f"Invalid player: {player}")
        if not 0 <= slot < LEGEND_SLOTS:
            raise StateError(f"Invalid legend slot: {slot} (0-{LEGEND_SLOTS - 1})")
        return self._state.legends[str(player)][slot]

    def set_legend(
        self,
        player: int,
        slot: int,
        card_id: Optional[str],
        name: str = "",
        subtitle: str = "",
        image: str = "",
        revealed: Optional[bool] = None,
    ) -> GameEvent:
        """Assign a card to a legend slot (card_id=None clears it, hidden again)."""
        with self._lock:
            legend = self._legend_slot(player, slot)
            if card_id is None:
                description = f"P{player} legend {slot + 1} cleared"
                self._push_undo(description)
                legend.upside_down = False
                legend.card_id = None
                legend.name = ""
                legend.subtitle = ""
                legend.image = ""
                legend.revealed = False
            else:
                description = f"P{player} legend {slot + 1} set: {name}"
                self._push_undo(description)
                if legend.card_id != card_id:
                    legend.upside_down = False
                legend.card_id = card_id
                legend.name = name
                legend.subtitle = subtitle
                legend.image = image
                if revealed is not None:
                    legend.revealed = revealed
            event = self._record_event(
                "legend_set", description,
                {"player": player, "slot": slot, "card_id": card_id},
            )
            log.info("LEGEND_SET player=%s slot=%s card=%s", player, slot, card_id)
            return event

    def observe_legend(self, player, slot, card_id, name="", subtitle="", image="", upside_down=False):
        """Apply identity, position and orientation together; never duplicate a moved card."""
        with self._lock:
            current = self._legend_slot(player, slot)
            slots = self._state.legends[str(player)]
            source = next((i for i, item in enumerate(slots) if item.card_id == card_id), None)
            if current.card_id == card_id and current.revealed and current.upside_down == upside_down:
                return None
            description = f"P{player} legend {slot + 1} observed: {name}"
            self._push_undo(description)
            if source is not None and source != slot:
                slots[source], slots[slot] = slots[slot], slots[source]
            elif current.card_id != card_id:
                slots[slot] = LegendSlot(card_id=card_id, name=name, subtitle=subtitle, image=image)
            slots[slot].revealed = True
            slots[slot].upside_down = bool(upside_down)
            return self._record_event("legend_observed", description,
                                      {"player": player, "slot": slot, "from_slot": source,
                                       "card_id": card_id, "upside_down": bool(upside_down)})

    def swap_legends(self, player: int, slot_a: int, slot_b: int) -> GameEvent:
        """Swap two of a player's legend slots (card + revealed state travel together)."""
        with self._lock:
            a = self._legend_slot(player, slot_a)
            b = self._legend_slot(player, slot_b)
            if slot_a == slot_b:
                raise StateError("Pick two different legend slots to swap")
            description = f"P{player} legends {slot_a + 1} ↔ {slot_b + 1}"
            self._push_undo(description)
            slots = self._state.legends[str(player)]
            slots[slot_a], slots[slot_b] = b, a
            event = self._record_event(
                "legends_swapped", description,
                {"player": player, "slots": [slot_a, slot_b]},
            )
            log.info("LEGENDS_SWAPPED player=%s a=%s b=%s", player, slot_a, slot_b)
            return event

    def reveal_legend(self, player: int, slot: int, revealed: bool) -> GameEvent:
        with self._lock:
            legend = self._legend_slot(player, slot)
            if legend.card_id is None and revealed:
                raise StateError(f"P{player} legend {slot + 1} has no card assigned")
            if legend.revealed == revealed:
                raise StateError(f"P{player} legend {slot + 1} already {'revealed' if revealed else 'hidden'}")
            description = f"P{player} legend {slot + 1} {'revealed' if revealed else 'hidden'}" + (
                f": {legend.name}" if revealed and legend.name else "")
            self._push_undo(description)
            legend.revealed = revealed
            event = self._record_event(
                "legend_revealed", description,
                {"player": player, "slot": slot, "revealed": revealed, "card_id": legend.card_id},
            )
            log.info("LEGEND_REVEALED player=%s slot=%s revealed=%s", player, slot, revealed)
            return event

    def set_street_cred(self, player: int, value: int) -> GameEvent:
        with self._lock:
            if player not in (1, 2):
                raise StateError(f"Invalid player: {player}")
            if not 0 <= value <= 99:
                raise StateError(f"Street cred must be 0-99, got {value}")
            attr = f"player{player}_cred"
            previous = getattr(self._state.match, attr)
            if previous == value:
                raise StateError(f"P{player} street cred is already {value}")
            description = f"P{player} street cred: {previous} → {value}"
            self._push_undo(description)
            # The operator sets the displayed total; store it as an adjustment
            # on top of the derived gig total so later dice changes keep it.
            setattr(self._state.match, f"player{player}_cred_adjust", value - self.gig_total(player))
            self._recompute_cred()
            event = self._record_event(
                "cred_changed", description, {"player": player, "value": value},
            )
            log.info("CRED_CHANGED player=%s value=%s", player, value)
            return event

    # --------------------------------------------------------------- match

    def set_player_names(self, player1_name: str, player2_name: str) -> GameEvent:
        with self._lock:
            description = f"Names set: {player1_name} vs {player2_name}"
            self._push_undo(description)
            self._state.match.player1_name = player1_name.strip() or "Player 1"
            self._state.match.player2_name = player2_name.strip() or "Player 2"
            event = self._record_event("names_set", description, {})
            log.info("NAMES_SET p1=%s p2=%s", player1_name, player2_name)
            return event

    def start_match(self, player1_name: Optional[str] = None, player2_name: Optional[str] = None) -> GameEvent:
        with self._lock:
            description = "Match started"
            self._push_undo(description)
            if player1_name is not None:
                self._state.match.player1_name = player1_name.strip() or "Player 1"
            if player2_name is not None:
                self._state.match.player2_name = player2_name.strip() or "Player 2"
            self._state.match.started = True
            event = self._record_event("match_started", description, {})
            log.info(
                "MATCH_STARTED p1=%s p2=%s",
                self._state.match.player1_name, self._state.match.player2_name,
            )
            return event

    def swap_sides(self) -> GameEvent:
        """Swap camera/player mapping only. Die ownership never changes."""
        with self._lock:
            swapped = not self._state.match.sides_swapped
            description = f"Sides swapped: {'on' if swapped else 'off'}"
            self._push_undo(description)
            self._state.match.sides_swapped = swapped
            event = self._record_event("sides_swapped", description, {"sides_swapped": swapped})
            log.info("SIDES_SWAPPED value=%s", swapped)
            return event

    def reset_match(self, *, start: bool = False) -> GameEvent:
        with self._lock:
            description = "New match started" if start else "Match reset"
            self._push_undo(description)
            kept_match = MatchInfo(
                started=start,
                player1_name=self._state.match.player1_name,
                player2_name=self._state.match.player2_name,
            )
            self._state = self._initial_state(match=kept_match)
            event = self._record_event("reset", description, {})
            log.info("MATCH_RESET")
            return event

    # ------------------------------------------------------------ history

    def undo(self) -> GameEvent:
        with self._lock:
            if not self._undo_stack:
                raise StateError("Nothing to undo")
            description, snapshot = self._undo_stack.pop()
            self._redo_stack.append((description, self._state.model_copy(deep=True)))
            self._state = snapshot
            log.info("UNDO action=%s", description)
            return GameEvent(
                type="undo",
                description=f"Undo: {description}",
                timestamp=_now(),
                data={"undone": description},
            )

    def redo(self) -> GameEvent:
        with self._lock:
            if not self._redo_stack:
                raise StateError("Nothing to redo")
            description, snapshot = self._redo_stack.pop()
            self._undo_stack.append((description, self._state.model_copy(deep=True)))
            self._state = snapshot
            log.info("REDO action=%s", description)
            return GameEvent(
                type="redo",
                description=f"Redo: {description}",
                timestamp=_now(),
                data={"redone": description},
            )
