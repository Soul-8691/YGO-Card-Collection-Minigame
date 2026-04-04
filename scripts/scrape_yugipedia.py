#!/usr/bin/env python3
"""
Scrape Yu-Gi-Oh! set card lists from Yugipedia.

Parses https://yugipedia.com/wiki/Set_chronology, follows each set link,
fetches the corresponding Set_Card_Lists subpage (OCG-JP or TCG-EN), and writes
card names + rarities to JSON files.

Requires: mwparserfromhell  (pip install mwparserfromhell)

Output: output/card_lists/{set_name}_{ocg|tcg}.json
Format: { "Card Name": ["Rarity1", ...], ... }
"""

import json
import re
import time
import urllib.request
import urllib.parse
from pathlib import Path

import mwparserfromhell

SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR.parent / "output" / "card_lists"
API_BASE = "https://yugipedia.com/api.php"
REQUEST_DELAY = 0.5  # seconds between API requests


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fetch_wikitext(page_title):
    """Return raw wikitext string for a Yugipedia page, or None if not found."""
    params = {
        "action": "parse",
        "page": page_title,
        "prop": "wikitext",
        "format": "json",
    }
    url = f"{API_BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("parse", {}).get("wikitext", {}).get("*")
    except Exception:
        return None


def safe_filename(name):
    """Replace characters that are invalid in filenames."""
    return re.sub(r'[<>:"/\\|?*]', "-", name)


# ---------------------------------------------------------------------------
# Parse Set_chronology → {set_page_name: "ocg" | "tcg"}
# ---------------------------------------------------------------------------

def get_sets_from_chronology():
    """
    Parse Set_chronology and return an ordered dict of
    { set_page_name: "ocg" | "tcg" }.
    Rush Duel and other non-OCG/TCG sections are ignored.
    """
    wikitext = fetch_wikitext("Set_chronology")
    if not wikitext:
        raise RuntimeError("Could not fetch Set_chronology")
    time.sleep(REQUEST_DELAY)

    wikicode = mwparserfromhell.parse(wikitext)
    sets = {}

    for section in wikicode.get_sections(levels=[2]):
        headings = section.filter_headings()
        if not headings:
            continue
        heading_text = headings[0].title.strip_code().strip().lower()

        if "ocg" in heading_text:
            region = "ocg"
        elif "tcg" in heading_text:
            region = "tcg"
        else:
            continue  # Rush Duel, etc.

        # Table rows have two formats depending on the series:
        #   Series 1 OCG:   |[[Set Name]] || Type || Date || Notes
        #   Series 2+ OCG and all TCG:  | Abbr || [[Set Name]] || Type || Date || Notes
        # In both cases the set name is the FIRST [[link]] in the row.
        section_str = str(section)
        for line in section_str.splitlines():
            stripped = line.lstrip()
            # Only consider table data rows (start with |, but not ||, |-, |}, |!)
            if not stripped.startswith("|"):
                continue
            if stripped[:2] in ("||", "|-", "|}", "|!") or stripped.startswith("! "):
                continue
            m = re.search(r"\[\[([^\|\]]+?)(?:\|[^\]]+)?\]\]", stripped)
            if m:
                name = m.group(1).strip()
                if name and not name.startswith(("File:", "Category:", "Template:")):
                    sets[name] = region

    return sets


# ---------------------------------------------------------------------------
# Parse {{Set list}} template → {card_name: [rarities]}
# ---------------------------------------------------------------------------

# Card code pattern: e.g. LOB-EN001, V1-JP040, DPKB-EN000
_CODE_RE = re.compile(r"^[A-Z][A-Z0-9]*-[A-Z]{0,3}[0-9]+$")


def parse_set_list_template(template):
    """
    Parse one {{Set list}} template and return {card_name: [rarities]}.

    Card list body lines can be:
      Card Name
      Card Name; Rarity
      Card Code; Card Name; Rarity
      Card Code; Card Name; Rarity // printed-name::... or other annotations
    """
    # Default rarity specified in |rarities= param (comma-separated)
    default_rarities = ["Common"]
    if template.has("rarities"):
        raw = str(template.get("rarities").value).strip()
        parsed = [r.strip() for r in raw.split(",") if r.strip()]
        if parsed:
            default_rarities = parsed

    # The card list is the first unnamed (positional) parameter
    body = None
    for param in template.params:
        if not param.showkey:
            body = str(param.value)
            break

    if not body:
        return {}

    cards = {}
    for raw_line in body.splitlines():
        # Strip // annotations (printed-name, image, alt, etc.)
        if "//" in raw_line:
            raw_line = raw_line[: raw_line.index("//")]
        line = raw_line.strip()
        if not line:
            continue

        fields = [f.strip() for f in line.split(";")]
        # Drop trailing empty fields
        while fields and not fields[-1]:
            fields.pop()
        if not fields:
            continue

        # Determine field layout based on count and whether first field is a code
        if len(fields) >= 3 and _CODE_RE.match(fields[0]):
            # Code; Name; Rarity [; ...]
            name_raw = fields[1]
            rarity = fields[2] or None
        elif len(fields) >= 2 and _CODE_RE.match(fields[0]):
            # Code; Name  (no explicit rarity)
            name_raw = fields[1]
            rarity = None
        elif len(fields) >= 2:
            # Name; Rarity
            name_raw = fields[0]
            rarity = fields[1] or None
        else:
            # Name only
            name_raw = fields[0]
            rarity = None

        rarities = [rarity] if rarity else default_rarities

        # Strip any residual wiki markup from the name
        name = mwparserfromhell.parse(name_raw).strip_code().strip()
        if not name:
            continue

        if name in cards:
            for r in rarities:
                if r not in cards[name]:
                    cards[name].append(r)
        else:
            cards[name] = list(rarities)

    return cards


# ---------------------------------------------------------------------------
# Fetch and aggregate all {{Set list}} templates from a subpage
# ---------------------------------------------------------------------------

def fetch_card_list(set_name, region):
    """
    Try to fetch the Set_Card_Lists subpage for a set and parse all
    {{Set list}} templates found there.

    For OCG sets: tries (OCG-JP).
    For TCG sets: tries (TCG-EN), (TCG-NA), (TCG-E), (TCG-A) in order.

    Returns {card_name: [rarities]} or None if the subpage was not found.
    """
    suffixes = ["OCG-JP"] if region == "ocg" else ["TCG-EN", "TCG-NA", "TCG-E", "TCG-A"]

    for suffix in suffixes:
        subpage = f"Set_Card_Lists:{set_name} ({suffix})"
        wikitext = fetch_wikitext(subpage)
        time.sleep(REQUEST_DELAY)

        if not wikitext:
            continue

        wikicode = mwparserfromhell.parse(wikitext)
        all_cards = {}

        for tmpl in wikicode.filter_templates():
            if tmpl.name.strip().lower() == "set list":
                for name, rarities in parse_set_list_template(tmpl).items():
                    if name in all_cards:
                        for r in rarities:
                            if r not in all_cards[name]:
                                all_cards[name].append(r)
                    else:
                        all_cards[name] = list(rarities)

        if all_cards:
            return all_cards

    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching Set_chronology...")
    sets = get_sets_from_chronology()
    print(f"Found {len(sets)} sets (OCG + TCG)\n")

    total = len(sets)
    for i, (set_name, region) in enumerate(sets.items(), 1):
        out_path = OUTPUT_DIR / f"{safe_filename(set_name)}_{region}.json"

        if out_path.exists():
            print(f"[{i}/{total}] SKIP  {set_name}")
            continue

        print(f"[{i}/{total}] {region.upper()}  {set_name}...", end="", flush=True)

        cards = fetch_card_list(set_name, region)

        if cards is None:
            print("  not found")
            continue

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(cards, f, indent=2, ensure_ascii=False)

        print(f"  {len(cards)} cards  →  {out_path.name}")

    print("\nDone.")


if __name__ == "__main__":
    main()
