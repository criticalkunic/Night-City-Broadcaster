"""Pydantic models for authoritative game state."""
from typing import Optional

from pydantic import BaseModel, Field

# Die type -> number of sides. Every physical die is uniquely owned.
DIE_TYPES = {"d4": 4, "d6": 6, "d8": 8, "d10": 10, "d12": 12, "d20": 20}

# Locations are data, not code — new areas can be added without touching logic.
DEFAULT_LOCATIONS = ["p1_fixer", "p1_gig", "p2_fixer", "p2_gig"]

LOCATION_LABELS = {
    "p1_fixer": "Player 1 Fixer Area",
    "p1_gig": "Player 1 Gig Area",
    "p2_fixer": "Player 2 Fixer Area",
    "p2_gig": "Player 2 Gig Area",
}


class Die(BaseModel):
    id: str
    owner: int = Field(ge=1, le=2)
    type: str
    location: str
    last_roll: Optional[int] = None


class LatestCard(BaseModel):
    player: int = Field(ge=1, le=2)
    card_id: str
    name: str
    subtitle: str = ""
    image: str = ""
    matched_image: str = ""
    source: str = "manual"  # "manual" | "vision"
    confidence: Optional[float] = None
    timestamp: str


class MatchInfo(BaseModel):
    player1_name: str = "Player 1"
    player2_name: str = "Player 2"
    # Street cred = the combined value of the gigs a player controls (sum of
    # the roll values of every die in that player's gig area) + a manual
    # operator adjustment. Derived on every dice change; never edited directly.
    player1_cred: int = 0
    player2_cred: int = 0
    player1_cred_adjust: int = 0
    player2_cred_adjust: int = 0
    started: bool = False
    # Camera/player mapping flag only — die ownership never changes on swap.
    sides_swapped: bool = False


class LegendSlot(BaseModel):
    """One of a player's three legend cards. Hidden until revealed."""
    card_id: Optional[str] = None
    name: str = ""
    subtitle: str = ""
    image: str = ""
    matched_image: str = ""
    revealed: bool = False
    upside_down: bool = False


class GameEvent(BaseModel):
    type: str
    description: str
    timestamp: str
    data: dict = Field(default_factory=dict)


class GameState(BaseModel):
    card_play_history: list[Optional[LatestCard]] = Field(default_factory=list)
    last_played_card: Optional[LatestCard] = None
    awaiting_first_play: bool = False
    match: MatchInfo
    # Last card each player played, keyed "1"/"2" (JSON object keys).
    latest_cards: dict[str, Optional[LatestCard]]
    # Three legend slots per player, keyed "1"/"2".
    legends: dict[str, list[LegendSlot]]
    dice: dict[str, Die]
    recent_events: list[GameEvent] = Field(default_factory=list)
    locations: list[str]
