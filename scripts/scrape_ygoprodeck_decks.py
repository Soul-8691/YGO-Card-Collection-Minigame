#!/usr/bin/env python3
"""
Scrape tournament meta decks from ygoprodeck.com and save as .ydk files.

Uses the internal /api/decks/getDecks.php endpoint (20 decks per page, offset-based)
to enumerate all decks, then writes each as a .ydk file to output/decks/ygoprodeck/.
Card IDs are annotated with names from output/cardinfo.json.

Requires: requests  (pip install requests)
"""

import json
import re
import time
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
OUTPUT_DIR = ROOT_DIR / "output" / "decks" / "ygoprodeck"
CARDINFO_FILE = ROOT_DIR / "output" / "cardinfo.json"

DECKS_API = "https://ygoprodeck.com/api/decks/getDecks.php"
FORMAT = "tournament%20meta%20decks"
PAGE_SIZE = 20
REQUEST_DELAY = 1.0  # seconds between requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://ygoprodeck.com/",
}


def safe_filename(name):
    return re.sub(r'[<>:"/\\|?*\r\n]', "-", name).strip()


def get_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def load_cardinfo():
    """Return dict of card_id (str) -> card_name from output/cardinfo.json."""
    if not CARDINFO_FILE.exists():
        return {}
    with open(CARDINFO_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return {str(card["id"]): card["name"] for card in data["data"]}


def fetch_deck_page(session, offset):
    """Fetch one page of decks from the API. Returns list of deck dicts."""
    url = f"{DECKS_API}?format={FORMAT}&offset={offset}&limit={PAGE_SIZE}"
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def build_ydk(deck, id_to_name):
    """Assemble a .ydk file string from a deck dict, with name comments."""
    def ids_from(field):
        raw = deck.get(field) or "[]"
        if isinstance(raw, list):
            return raw
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []

    def fmt(card_id):
        cid = str(card_id).strip()
        name = id_to_name.get(cid)
        return f"{cid} --  {name}" if name else cid

    main_ids = ids_from("main_deck")
    extra_ids = ids_from("extra_deck")
    side_ids = ids_from("side_deck")

    lines = ["#main"]
    lines.extend(fmt(i) for i in main_ids)
    lines.append("#extra")
    lines.extend(fmt(i) for i in extra_ids)
    lines.append("!side")
    lines.extend(fmt(i) for i in side_ids)
    return "\n".join(lines) + "\n"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    id_to_name = load_cardinfo()
    if id_to_name:
        print(f"Loaded {len(id_to_name)} card names from {CARDINFO_FILE}")
    else:
        print(f"Warning: {CARDINFO_FILE} not found, card name comments will be omitted")

    session = get_session()

    seen_ids = set()
    downloaded = 0
    skipped = 0
    offset = 0

    print("Fetching tournament meta decks...\n")

    while offset < 2000:
        print(f"  offset={offset}...", end="", flush=True)
        decks = fetch_deck_page(session, offset)

        if not decks:
            print(" empty response, done.")
            break

        new_this_page = 0
        for deck in decks:
            deck_num = str(deck.get("deckNum", ""))
            if deck_num in seen_ids:
                continue
            seen_ids.add(deck_num)
            new_this_page += 1

            deck_name = deck.get("deck_name", f"deck_{deck_num}")
            filename = f"{safe_filename(deck_name)}_{deck_num}.ydk"
            out_path = OUTPUT_DIR / filename

            if out_path.exists():
                skipped += 1
                continue

            ydk_content = build_ydk(deck, id_to_name)
            out_path.write_text(ydk_content, encoding="utf-8")
            downloaded += 1

        print(f" {new_this_page} new  (total seen: {len(seen_ids)})")

        # The API wraps around rather than returning empty — stop when no new decks
        if new_this_page == 0:
            print("No new decks on this page, done.")
            break

        offset += PAGE_SIZE
        time.sleep(REQUEST_DELAY)

    print(f"\nDone. Downloaded: {downloaded}  Skipped (already existed): {skipped}")


if __name__ == "__main__":
    main()
