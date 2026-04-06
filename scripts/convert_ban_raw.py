#!/usr/bin/env python3
"""
Convert a ban list JSON from raw format (ban amount as top-level key, card
objects with "nameeng") to name format (card name -> ban amount int).

Usage:
    python scripts/convert_ban_raw.py <input.raw.json> <output.json>
"""

import json
import sys
from pathlib import Path

BAN_KEYS = {"0", "1", "2", "3"}


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.raw.json> <output.json>")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    with input_path.open(encoding="utf-8") as f:
        raw = json.load(f)

    result = {}
    for key in BAN_KEYS:
        if key not in raw:
            continue
        ban_amount = int(key)
        for card in raw[key]:
            name = card.get("nameeng")
            if name:
                result[name] = ban_amount

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(result)} cards -> {output_path}")


if __name__ == "__main__":
    main()
