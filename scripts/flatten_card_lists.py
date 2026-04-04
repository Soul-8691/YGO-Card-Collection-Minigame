#!/usr/bin/env python3
"""
Flatten all card list JSONs into a single TSV.

Iterates every .json file in output/card_lists/, and for each card and each
rarity writes one tab-separated line to output/set_chronology.tsv:

    set_name  card_name  rarity

where set_name is the JSON filename (without .json extension).

Usage:
    python scripts/flatten_card_lists.py
"""

import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
INPUT_DIR = ROOT_DIR / "output" / "card_lists"
OUTPUT_FILE = ROOT_DIR / "output" / "set_chronology.tsv"


def main():
    json_files = sorted(INPUT_DIR.glob("*.json"))
    print(f"Found {len(json_files)} JSON files in {INPUT_DIR}")

    row_count = 0
    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as out:
        out.write("set_name\tcard_name\trarity\n")
        for json_path in json_files:
            set_name = json_path.stem  # filename without .json
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
            for card_name, rarities in data.items():
                for rarity in rarities:
                    out.write(f"{set_name}\t{card_name}\t{rarity}\n")
                    row_count += 1

    print(f"Wrote {row_count} rows to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
