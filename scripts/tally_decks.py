#!/usr/bin/env python3
"""
Count card usage across video game decks matching a search keyword.

Searches the first line of every .ydk in output/decks/video_games/ (recursively)
for the given keyword (case-insensitive). For each matching deck, counts how many
times each card ID appears across all sections (main/extra/side). Card IDs are
resolved to names via output/cardinfo.json. Counts for IDs that share a name are
merged. Results are written to output/{keyword}.tsv, sorted by count descending.

Usage:
    python scripts/tally_decks.py <keyword>

Example:
    python scripts/tally_decks.py "Joey Wheeler"
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
DECKS_DIR = ROOT_DIR / "output" / "decks" / "video_games"
CARDINFO_FILE = ROOT_DIR / "cardinfo.json"

_ID_RE = re.compile(r"^(\d+)")


def load_cardinfo(path):
    """Return dict of card_id (int) -> card_name."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {card["id"]: card["name"] for card in data["data"]}


def parse_ydk(path):
    """
    Return (first_line_comment, id_counts) where id_counts is Counter of card IDs.
    first_line_comment is the raw first line (stripped, including the leading #).
    """
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        return ("", {})

    first_line = lines[0].strip()
    id_counts = defaultdict(int)

    for line in lines[1:]:
        line = line.strip()
        m = _ID_RE.match(line)
        if m:
            id_counts[int(m.group(1))] += 1

    return first_line, dict(id_counts)


def main():
    if len(sys.argv) < 2:
        print("Usage: python tally_decks.py <keyword>")
        sys.exit(1)

    keyword = " ".join(sys.argv[1:])
    keyword_lower = keyword.lower()
    output_file = ROOT_DIR / "output" / f"{keyword}.tsv"

    print(f"Loading card data from {CARDINFO_FILE}...")
    id_to_name = load_cardinfo(CARDINFO_FILE)
    print(f"  {len(id_to_name)} cards loaded")

    ydk_files = list(DECKS_DIR.rglob("*.ydk"))
    print(f"Scanning {len(ydk_files)} .ydk files for '{keyword}'...")

    # card_name -> total count across all matching decks
    name_counts = defaultdict(int)
    matched_decks = 0
    unknown_ids = set()

    for ydk_path in ydk_files:
        first_line, id_counts = parse_ydk(ydk_path)
        if keyword_lower not in first_line.lower():
            continue

        matched_decks += 1
        for card_id, count in id_counts.items():
            name = id_to_name.get(card_id)
            if name is None:
                unknown_ids.add(card_id)
                name = str(card_id)
            name_counts[name] += count

    print(f"  Matched {matched_decks} deck(s)")

    if unknown_ids:
        print(f"  Warning: {len(unknown_ids)} unrecognised card ID(s): {sorted(unknown_ids)[:10]}{'...' if len(unknown_ids) > 10 else ''}")

    sorted_cards = sorted(name_counts.items(), key=lambda x: x[1], reverse=True)

    print(f"Writing {len(sorted_cards)} entries to {output_file}...")
    with open(output_file, "w", encoding="utf-8", newline="") as f:
        f.write("card_name\tcount\n")
        for name, count in sorted_cards:
            f.write(f"{name}\t{count}\n")

    print("Done.")


if __name__ == "__main__":
    main()
