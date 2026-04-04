#!/usr/bin/env python3
"""Convert chimeratech_card_usage.json into a TSV with one row per unique card,
including weighted columns based on December 2006 banlist restrictions."""

from __future__ import annotations

import json
import sys

INPUT_PATH = "output/card_usage.json"
BANLIST_PATH = "output/december_2006_banlist.json"
OUTPUT_PATH = "output/card_usage.tsv"

RESTRICTION_WEIGHT = {
    "limited": 3.0,
    "semiLimited": 1.5,
}


def build_lookup(entries: list[dict]) -> dict[str, int]:
    return {e["name"]: e["count"] for e in entries}


def build_weight_map(banlist_path: str) -> dict[str, float]:
    """Map card name -> weight multiplier from the banlist JSON."""
    with open(banlist_path, "r", encoding="utf-8") as f:
        banlist = json.load(f)
    weights: dict[str, float] = {}
    for key, multiplier in RESTRICTION_WEIGHT.items():
        for entry in banlist.get(key, []):
            name = entry.get("cardName")
            if name:
                weights[name] = multiplier
    return weights


def weighted(count: int, weight: float) -> float:
    return round(count * weight, 1)


def fmt(val: float) -> str:
    return str(int(val)) if val == int(val) else str(val)


def main() -> None:
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    main_map = build_lookup(data.get("main", []))
    side_map = build_lookup(data.get("side", []))
    extra_map = build_lookup(data.get("extra", []))
    total_map = build_lookup(data.get("total", []))

    weight_map = build_weight_map(BANLIST_PATH)

    all_names = sorted(
        set(main_map) | set(side_map) | set(extra_map) | set(total_map)
    )

    header = "name\tmain\tside\textra\ttotal\tmain_weighted\tside_weighted\textra_weighted\ttotal_weighted\n"
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(header)
        for name in all_names:
            m = main_map.get(name, 0)
            s = side_map.get(name, 0)
            e = extra_map.get(name, 0)
            t = total_map.get(name, 0)
            w = weight_map.get(name, 1.0)
            mw = weighted(m, w)
            sw = weighted(s, w)
            ew = weighted(e, w)
            tw = weighted(t, w)
            f.write(f"{name}\t{m}\t{s}\t{e}\t{t}\t{fmt(mw)}\t{fmt(sw)}\t{fmt(ew)}\t{fmt(tw)}\n")

    print(f"Wrote {len(all_names)} rows to {OUTPUT_PATH}", file=sys.stderr)
    limited = [n for n in all_names if weight_map.get(n) == 3.0]
    semi = [n for n in all_names if weight_map.get(n) == 1.5]
    print(f"  Weighted cards: {len(limited)} limited (x3), {len(semi)} semi-limited (x1.5)", file=sys.stderr)


if __name__ == "__main__":
    main()
