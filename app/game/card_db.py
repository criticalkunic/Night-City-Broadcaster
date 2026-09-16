"""Local card database. Read-only at runtime; populated by scripts/import_cards.py."""
import json
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("app.cards")


class CardDatabase:
    def __init__(self, path: Path):
        self.path = path
        self.cards: list[dict] = []
        self._by_id: dict[str, dict] = {}
        self.reload()

    def reload(self) -> None:
        if not self.path.exists():
            log.warning("CARD_DB_MISSING path=%s", self.path)
            self.cards = []
            self._by_id = {}
            return
        self.cards = json.loads(self.path.read_text(encoding="utf-8"))
        self._by_id = {card["id"]: card for card in self.cards}
        log.info("CARD_DB_LOADED path=%s cards=%s", self.path, len(self.cards))

    def get(self, card_id: str) -> Optional[dict]:
        return self._by_id.get(card_id)

    def search(self, query: str, limit: int = 20, card_type: Optional[str] = None) -> list[dict]:
        """Name/alias/subtitle prefix + substring search. card_type ("Legend",
        "Unit", ...) restricts results to that type, case-insensitively."""
        q = query.strip().lower()
        wanted = (card_type or "").strip().lower()
        pool = [c for c in self.cards if not wanted or (c.get("card_type") or "").lower() == wanted]
        if not q:
            return pool[:limit]
        scored: list[tuple[int, dict]] = []
        for card in pool:
            name = card.get("name", "").lower()
            subtitle = card.get("subtitle", "").lower()
            aliases = [a.lower() for a in card.get("aliases", [])]
            if name.startswith(q):
                scored.append((0, card))
            elif q in name:
                scored.append((1, card))
            elif any(q in a for a in aliases):
                scored.append((2, card))
            elif q in subtitle:
                scored.append((3, card))
        scored.sort(key=lambda item: (item[0], item[1].get("name", "")))
        return [card for _, card in scored[:limit]]
