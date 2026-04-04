#!/usr/bin/env python3
"""
Collect every distinct rarity value from all JSON files in output/card_lists/
and write them sorted to rarities.txt.

Usage:
    python scripts/collect_rarities.py
"""

import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
INPUT_DIR = ROOT_DIR / "output" / "card_lists"
CARDINFO_FILE = ROOT_DIR / "output" / "cardinfo.json"
OUTPUT_FILE = ROOT_DIR / "output/rarities.txt"


def load_card_names(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {card["name"] for card in data["data"]}


def main():
    card_names = load_card_names(CARDINFO_FILE)

    rarities = set()

    for json_path in INPUT_DIR.glob("*.json"):
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        for values in data.values():
            rarities.update(values)

    rarities -= card_names

    sorted_rarities = sorted(rarities, key=str.lower)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted_rarities) + "\n")

    print(f"Found {len(sorted_rarities)} distinct rarities -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
