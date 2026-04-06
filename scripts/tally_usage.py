#!/usr/bin/env python3
"""Tally card usage across all Chimeratech format top-cut decks from Format Library."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict

GALLERY_URL = "https://formatlibrary.com/api/events/gallery/reaper"
EVENT_URL = "https://formatlibrary.com/api/events/{abbrev}"
DECK_URL = "https://formatlibrary.com/api/decks/{deck_id}"
UA = "Mozilla/5.0 (compatible; YGOrange-tally/1.0)"
OUTPUT_PATH = "output/card_usage.json"
DELAY = 0.15


def fetch_json(url: str, timeout: int = 30) -> dict | list:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def tally_section(cards: list[dict], counter: dict[str, int]) -> None:
    for card in cards:
        name = card.get("name")
        if name:
            counter[name] += 1


def sorted_tally(counter: dict[str, int]) -> list[dict]:
    return [{"name": k, "count": v} for k, v in sorted(counter.items(), key=lambda x: -x[1])]


def main() -> None:
    print("Fetching gallery...", file=sys.stderr)
    gallery = fetch_json(GALLERY_URL)
    events = gallery.get("events", [])
    print(f"  Found {len(events)} events", file=sys.stderr)

    main_tally: dict[str, int] = defaultdict(int)
    side_tally: dict[str, int] = defaultdict(int)
    extra_tally: dict[str, int] = defaultdict(int)
    total_tally: dict[str, int] = defaultdict(int)
    decks_processed = 0

    for ev_idx, event in enumerate(events, 1):
        abbrev = event.get("abbreviation")
        if not abbrev:
            continue
        print(f"[{ev_idx}/{len(events)}] Event: {abbrev}", file=sys.stderr)
        time.sleep(DELAY)

        try:
            event_data = fetch_json(EVENT_URL.format(abbrev=abbrev))
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            print(f"  Error fetching event {abbrev}: {e}", file=sys.stderr)
            continue

        top_decks = event_data.get("topDecks", [])
        print(f"  {len(top_decks)} top decks", file=sys.stderr)

        for deck_entry in top_decks:
            deck_id = deck_entry.get("id")
            if deck_id is None:
                continue
            time.sleep(DELAY)

            try:
                deck_data = fetch_json(DECK_URL.format(deck_id=deck_id))
            except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
                print(f"  Error fetching deck {deck_id}: {e}", file=sys.stderr)
                continue

            deck_main = defaultdict(int)
            deck_side = defaultdict(int)
            deck_extra = defaultdict(int)

            tally_section(deck_data.get("main", []), deck_main)
            tally_section(deck_data.get("side", []), deck_side)
            tally_section(deck_data.get("extra", []), deck_extra)

            for name, count in deck_main.items():
                main_tally[name] += count
                total_tally[name] += count
            for name, count in deck_side.items():
                side_tally[name] += count
                total_tally[name] += count
            for name, count in deck_extra.items():
                extra_tally[name] += count

            decks_processed += 1

    result = {
        "decks_processed": decks_processed,
        "main": sorted_tally(main_tally),
        "side": sorted_tally(side_tally),
        "extra": sorted_tally(extra_tally),
        "total": sorted_tally(total_tally),
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent="\t", ensure_ascii=False)

    print(f"\nDone: {decks_processed} decks processed", file=sys.stderr)
    print(f"Unique cards — main: {len(main_tally)}, side: {len(side_tally)}, "
          f"extra: {len(extra_tally)}, total (main+side): {len(total_tally)}", file=sys.stderr)
    print(f"Results written to {OUTPUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
