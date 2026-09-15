"""Card database importer.

Runtime recognition never scrapes; this script is the only thing that writes
app/cards/cards.json and app/cards/images/. Pull the official card list:

    python scripts/import_cards.py --source cyberpunktcg
    python scripts/import_cards.py --source cyberpunktcg --force   # re-download images
    python scripts/import_cards.py --validate

Source: cyberpunktcg.com is a thin client over the netdeck.gg card API
(https://api.netdeck.gg/api/cards/cyberpunk?limit=N&offset=M). Each item
carries a signed CloudFront `image_url` (expires within days), so images are
downloaded immediately and stored locally; the DB never references remote
URLs at runtime.

Local schema (superset of what the operator UI and overlay read):

    id        stable card id (netdeck external_id, e.g. "cb-v-streetkid")
    name      card name           ("V")
    subtitle  card subname        ("Streetkid")
    image     local image path    ("/cards/images/cb-v-streetkid.webp")
    set       set code
    number    print number
    aliases   [display_name, slug words] for operator search
    card_type Legend | Unit | Gear | Program
    color, cost, power, ram, rules_text, flavor_text, rarity, artist,
    keywords, classifications, source_id, printing_id, url
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
CARDS_FILE = BASE_DIR / "app" / "cards" / "cards.json"
IMAGES_DIR = BASE_DIR / "app" / "cards" / "images"

import os
if os.environ.get("NCB_DATA_DIR"):
    from app.config import CARDS_FILE, CARD_IMAGES_DIR
    IMAGES_DIR = CARD_IMAGES_DIR

NETDECK_API = "https://api.netdeck.gg/api/cards/cyberpunk"
CARD_PAGE = "https://cyberpunktcg.com/cards/{slug}"
PAGE_SIZE = 100
USER_AGENT = "cyberpunk-broadcast/1.0 (card importer)"

CARD_SCHEMA_EXAMPLE = {
    "id": "cb-v-streetkid",
    "name": "V",
    "subtitle": "Streetkid",
    "image": "/cards/images/cb-v-streetkid.webp",
    "set": "welcometonightcityretail",
    "number": "005a",
    "aliases": ["V: Streetkid"],
    "card_type": "Legend",
}


# ------------------------------------------------------------------ fetch

def _get(url: str, retries: int = 3, timeout: float = 30.0) -> bytes:
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as res:
                return res.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            time.sleep(1.0 + attempt)
    raise RuntimeError(f"GET failed after {retries} attempts: {url}: {last}")


def fetch_netdeck_items(page_size: int = PAGE_SIZE) -> list[dict]:
    """Page through the netdeck card list until `total` is reached."""
    items: list[dict] = []
    offset = 0
    total: Optional[int] = None
    seen_pages = set()
    while total is None or offset < total:
        url = f"{NETDECK_API}?limit={page_size}&offset={offset}"
        data = json.loads(_get(url))
        page = data.get("items") or []
        total = int(data['total']) if data.get('total') is not None else None
        if not page:
            if total is not None and offset < total:
                raise RuntimeError('Card catalog download ended before all cards were received')
            break
        signature = json.dumps(page, sort_keys=True)
        if signature in seen_pages:
            raise RuntimeError('Card catalog source repeated a page')
        seen_pages.add(signature)
        items.extend(page)
        offset += len(page)
        print(f"  fetched {len(items)}/{total}")
    return items


# ------------------------------------------------------------ transform

def _num(value) -> Optional[int]:
    try:
        return None if value is None or value == "" else int(value)
    except (TypeError, ValueError):
        return None


def _image_ext(url: str) -> str:
    path = url.split("?", 1)[0].lower()
    for ext in (".webp", ".png", ".jpg", ".jpeg"):
        if path.endswith(ext):
            return ext
    return ".webp"


def netdeck_item_to_card(item: dict) -> Optional[dict]:
    """Map one netdeck API item onto the local card schema (image path only)."""
    card_id = item.get("external_id") or item.get("id") or item.get("slug")
    if not card_id:
        return None
    name = item.get("name") or item.get("display_name") or ""
    subtitle = item.get("subname") or ""
    display_name = item.get("display_name") or (f"{name}: {subtitle}" if subtitle else name)
    slug = item.get("slug") or ""
    image_url = item.get("image_url") or ""
    aliases = []
    if display_name and display_name != name:
        aliases.append(display_name)
    if slug:
        slug_words = slug.replace("-", " ")
        if slug_words.lower() not in (name.lower(), display_name.lower()):
            aliases.append(slug_words)
    card_set = item.get("set") or {}
    return {
        "id": card_id,
        "name": name,
        "subtitle": subtitle,
        "image": f"/cards/images/{card_id}{_image_ext(image_url)}" if image_url else "",
        "set": card_set.get("code") or "",
        "set_name": card_set.get("name") or "",
        "number": item.get("print_number") or "",
        "aliases": aliases,
        "card_type": item.get("card_type") or "",
        "color": item.get("color") or "",
        "cost": _num(item.get("cost")),
        "power": _num(item.get("power")),
        "ram": _num(item.get("ram")),
        "rules_text": item.get("rules_text") or "",
        "flavor_text": item.get("flavor_text") or "",
        "rarity": item.get("rarity") or "",
        "artist": item.get("artist") or "",
        "keywords": list(item.get("keywords") or []),
        "classifications": list(item.get("classifications") or []),
        "source_id": item.get("id") or "",
        "printing_id": item.get("printing_id") or "",
        "url": CARD_PAGE.format(slug=slug) if slug else "",
        "_image_url": image_url,  # stripped before writing
    }


def transform_items(items: Iterable[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for item in items:
        card = netdeck_item_to_card(item)
        if card is not None:
            seen[card["id"]] = card
    cards = list(seen.values())
    cards.sort(key=lambda c: (c["set"], c["number"], c["name"]))
    return cards


# -------------------------------------------------------------- import

def download_images(cards: list[dict], force: bool = False) -> tuple[int, int]:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = skipped = 0
    for card in cards:
        url = card.get("_image_url")
        if not url or not card["image"]:
            continue
        local = IMAGES_DIR / card["image"].removeprefix("/cards/images/")
        if local.exists() and local.stat().st_size > 0 and not force:
            skipped += 1
            continue
        try:
            local.write_bytes(_get(url))
            downloaded += 1
            print(f"  image {local.name}")
        except RuntimeError as exc:
            print(f"  WARN {card['id']}: {exc}")
            card["image"] = ""
    return downloaded, skipped


def write_cards(cards: list[dict]) -> None:
    clean = [{k: v for k, v in card.items() if not k.startswith("_")} for card in cards]
    CARDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CARDS_FILE.write_text(json.dumps(clean, indent=2, ensure_ascii=False) + "\n")


def prune_images(cards: list[dict]) -> int:
    """Delete images in IMAGES_DIR that no card references (old placeholders)."""
    referenced = {card["image"].removeprefix("/cards/images/") for card in cards if card.get("image")}
    removed = 0
    for path in IMAGES_DIR.iterdir():
        if path.is_file() and path.name not in referenced:
            path.unlink()
            removed += 1
    return removed


def import_cyberpunktcg(force: bool = False, prune: bool = False) -> int:
    print(f"Fetching card list from {NETDECK_API}")
    items = fetch_netdeck_items()
    if not items:
        print("ERROR no cards returned")
        return 1
    cards = transform_items(items)
    print(f"{len(cards)} cards; downloading images...")
    downloaded, skipped = download_images(cards, force=force)
    write_cards(cards)
    removed = prune_images(cards) if prune else 0
    print(f"wrote {CARDS_FILE} ({len(cards)} cards); images: {downloaded} downloaded, "
          f"{skipped} cached, {removed} pruned")
    return validate()


# ------------------------------------------------------------ validate

def validate() -> int:
    """Validate cards.json entries and confirm every referenced image exists."""
    cards = json.loads(CARDS_FILE.read_text())
    errors = 0
    seen_ids = set()
    for card in cards:
        for field in ("id", "name", "image"):
            if not card.get(field):
                print(f"ERROR {card.get('id', '?')}: missing {field}")
                errors += 1
        if card["id"] in seen_ids:
            print(f"ERROR duplicate id: {card['id']}")
            errors += 1
        seen_ids.add(card["id"])
        image = card.get("image", "")
        if image.startswith("/cards/images/"):
            local = IMAGES_DIR / image.removeprefix("/cards/images/")
            if not local.exists():
                print(f"ERROR {card['id']}: image not found: {local}")
                errors += 1
    print(f"{len(cards)} cards, {errors} errors")
    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--validate", action="store_true", help="validate existing cards.json")
    parser.add_argument("--source", choices=["cyberpunktcg"], help="import source")
    parser.add_argument("--force", action="store_true", help="re-download images that already exist")
    parser.add_argument("--prune", action="store_true", help="delete unreferenced images (old placeholders)")
    args = parser.parse_args()

    if args.validate:
        return validate()
    if args.source == "cyberpunktcg":
        return import_cyberpunktcg(force=args.force, prune=args.prune)
    parser.print_help()
    print("\nCard schema:")
    print(json.dumps(CARD_SCHEMA_EXAMPLE, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
