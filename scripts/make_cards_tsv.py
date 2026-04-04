#!/usr/bin/env python3
"""
Build cards.tsv from a card name list and a local cardinfo.json.

Usage:
    python scripts/make_cards_tsv.py <card_list.txt> [cardinfo.json] [output.tsv]

Defaults:
    cardinfo.json  -> <repo_root>/cardinfo.json
    output.tsv     -> <repo_root>/cards.tsv

cardinfo.json should be downloaded from:
    https://db.ygoprodeck.com/api/v7/cardinfo.php?misc=yes

TSV columns (tab-separated):
    name  type  attribute  race  level  atk  def  id  konami_id
"""

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent

COLUMNS = ["name", "type", "attribute", "race", "level", "atk", "def", "id", "konami_id"]


def load_card_names(path):
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def load_cardinfo(path):
    """Return a dict of lowercase(name) -> card dict."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    lookup = {}
    for card in data["data"]:
        lookup[card["name"].lower()] = card
    return lookup


def card_to_row(card):
    konami_id = ""
    misc = card.get("misc_info")
    if misc and isinstance(misc, list) and misc:
        konami_id = misc[0].get("konami_id", "")

    return [
        card.get("name", ""),
        card.get("type", ""),
        card.get("attribute", ""),
        card.get("race", ""),
        card.get("level", ""),
        card.get("atk", ""),
        card.get("def", ""),
        card.get("id", ""),
        konami_id,
    ]


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: python make_cards_tsv.py <card_list.txt> [cardinfo.json] [output.tsv]")
        sys.exit(1)

    card_list_file = Path(args[0])
    cardinfo_file = Path(args[1]) if len(args) > 1 else ROOT_DIR / "cardinfo.json"
    output_file = Path(args[2]) if len(args) > 2 else ROOT_DIR / "cards.tsv"

    print(f"Loading card names from {card_list_file}...")
    names = load_card_names(card_list_file)
    print(f"  {len(names)} names")

    print(f"Loading card data from {cardinfo_file}...")
    lookup = load_cardinfo(cardinfo_file)
    print(f"  {len(lookup)} cards in database")

    not_found = []
    rows = []
    for name in names:
        card = lookup.get(name.lower())
        if card is None:
            not_found.append(name)
            continue
        rows.append(card_to_row(card))

    print(f"Writing {len(rows)} rows to {output_file}...")
    with open(output_file, "w", encoding="utf-8", newline="") as f:
        f.write("\t".join(COLUMNS) + "\n")
        for row in rows:
            f.write("\t".join(str(v) if v is not None else "" for v in row) + "\n")

    if not_found:
        print(f"\nWarning: {len(not_found)} cards not found in cardinfo.json:")
        for name in not_found:
            print(f"  - {name}")

    print("Done.")


if __name__ == "__main__":
    main()
