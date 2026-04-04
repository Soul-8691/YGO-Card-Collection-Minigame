#!/usr/bin/env python3
"""
Count how many times each rarity in output/rarities.txt appears across all
card list JSONs in output/card_lists/, then write sorted counts to
output/rarity_counts.json (descending by count).

Usage:
    python scripts/count_rarities.py
"""

import json
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
INPUT_DIR = ROOT_DIR / "output" / "card_lists"
RARITIES_FILE = ROOT_DIR / "output" / "rarities.txt"
OUTPUT_FILE = ROOT_DIR / "output" / "rarity_counts.json"


def load_rarities(path):
    with open(path, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def main():
    rarities = load_rarities(RARITIES_FILE)

    counts = defaultdict(int)

    for json_path in INPUT_DIR.glob("*.json"):
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        for values in data.values():
            for rarity in values:
                if rarity in rarities:
                    counts[rarity] += 1

    sorted_counts = dict(
        sorted(counts.items(), key=lambda x: x[1], reverse=True)
    )

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted_counts, f, indent=2, ensure_ascii=False)

    print(f"Found {len(sorted_counts)} rarities -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
