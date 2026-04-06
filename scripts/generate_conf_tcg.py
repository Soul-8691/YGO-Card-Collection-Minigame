"""
Generate a TCG ban list .conf from a raw JSON ban list file.

Looks up card IDs via the YGOProDeck API and ban statuses from 2006-09-01.raw.json.
The raw JSON format has ban status as top-level keys ("0", "1", "2") with arrays of
card objects that contain "nameeng" for the English card name.
Output format matches Goat.conf: "{id} {ban_status} --{card_name}"
"""

import json
import time
import urllib.request
import urllib.parse
import urllib.error
import os
import sys

SCRIPT_DIR = os.getcwd()
CARD_LIST_FILE = os.path.join(SCRIPT_DIR, "output/reaper.txt")
BAN_LIST_FILE = os.path.join(SCRIPT_DIR, "ban/2005-09-01.raw.json")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "output/TCG-2005-09-01.conf")

API_BASE = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
BATCH_SIZE = 20  # How many card names to send per API request (pipe-separated)
REQUEST_DELAY = 0.15  # Seconds between API requests to stay under rate limit


def load_card_names(filepath):
    """Load card names from cards.txt, skipping blank lines and tokens."""
    names = []
    # Entries that are tokens or otherwise not real searchable cards
    token_keywords = ["Token"]

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            name = line.strip().strip("\r\n")
            if not name:
                continue
            # Skip token entries (they don't have real card IDs in the API)
            if any(name.endswith(f" {kw}") or name == kw for kw in token_keywords):
                continue
            names.append(name)
    return names


def load_ban_list(filepath):
    """Load ban statuses from a raw JSON file.

    The raw format has ban status as top-level string keys ("0", "1", "2"),
    each mapping to a list of card objects with a "nameeng" field.
    Returns dict of nameeng -> int status.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    ban_map = {}
    for status_str in ("0", "1", "2"):
        if status_str not in data:
            continue
        status = int(status_str)
        for card in data[status_str]:
            name = card.get("nameeng")
            if name:
                ban_map[name] = status
    return ban_map


def clean_name_for_api(name):
    """Clean card name for API lookup."""
    # Strip "(card)" suffix used to disambiguate in the source file
    if name.endswith(" (card)"):
        name = name[:-7]
    # Strip "(alternate password)" suffix
    if name.endswith(" (alternate password)"):
        name = name[:-20]
    return name


# Some cards in cards.txt use names that differ from the API's canonical names.
# Map from cards.txt name -> API name
NAME_OVERRIDES = {
    "Arcana Knight Joker": "Arcana Knight Joker",
    "Dark Magician (Arkana)": "Dark Magician",
    "Luster Dragon 2": "Luster Dragon #2",
    "Sasuke Samurai 2": "Sasuke Samurai #2",
    "Sasuke Samurai 3": "Sasuke Samurai #3",
    "Sasuke Samurai 4": "Sasuke Samurai #4",
    "Twin Long Rods 1": "Twin Long Rods #1",
    "Twin Long Rods 2": "Twin Long Rods #2",
    "Nekogal 1": "Nekogal #1",
    "Nekogal 2": "Nekogal #2",
    "Rock Ogre Grotto 1": "Rock Ogre Grotto #1",
    "Rock Ogre Grotto 2": "Rock Ogre Grotto #2",
    "Steel Ogre Grotto 1": "Steel Ogre Grotto #1",
    "Steel Ogre Grotto 2": "Steel Ogre Grotto #2",
    "Fiend Reflection 1": "Fiend Reflection #1",
    "Fiend Reflection 2": "Fiend Reflection #2",
    "M-Warrior 1": "M-Warrior #1",
    "M-Warrior 2": "M-Warrior #2",
    "Jinzo 7": "Jinzo #7",
    "Crawling Dragon 2": "Crawling Dragon #2",
    "Darkfire Soldier 1": "Darkfire Soldier #1",
    "Darkfire Soldier 2": "Darkfire Soldier #2",
    "Mystical Sheep 1": "Mystical Sheep #1",
    "Mystical Sheep 2": "Mystical Sheep #2",
    "Batteryman AA": "Batteryman AA",
    "Batteryman C": "Batteryman C",
    "Winged Dragon, Guardian of the Fortress 1": "Winged Dragon, Guardian of the Fortress #1",
    "Winged Dragon, Guardian of the Fortress 2": "Winged Dragon, Guardian of the Fortress #2",
    "Polymerization (alternate password)": None,  # Skip - duplicate
    "Key Mace 2": "Key Mace #2",
    "Mystical Sand": "Mystical Sand",
    "Slime Toad": "Slime Toad",
}


def get_api_name(original_name):
    """Get the name to use for API lookup."""
    if original_name in NAME_OVERRIDES:
        return NAME_OVERRIDES[original_name]
    return clean_name_for_api(original_name)


def fetch_card_batch(names):
    """Fetch card info for a batch of names from the API. Returns dict of name -> id."""
    query = "|".join(names)
    url = f"{API_BASE}?name={urllib.parse.quote(query)}"

    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "TCGConfGenerator/1.0")
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 400:
            # Card not found - try individually
            return {}
        raise

    results = {}
    if "data" in data:
        for card in data["data"]:
            results[card["name"]] = card["id"]
    return results


def fetch_single_card(name):
    """Fetch a single card's ID from the API."""
    url = f"{API_BASE}?name={urllib.parse.quote(name)}"
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "TCGConfGenerator/1.0")
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        if "data" in data and len(data["data"]) > 0:
            return data["data"][0]["id"]
    except urllib.error.HTTPError:
        pass
    return None


def main():
    print("Loading card names from cards.txt...")
    original_names = load_card_names(CARD_LIST_FILE)
    print(f"  Found {len(original_names)} card entries")

    print(f"Loading ban list from {os.path.basename(BAN_LIST_FILE)}...")
    ban_list = load_ban_list(BAN_LIST_FILE)
    print(f"  Found {len(ban_list)} banned/limited cards")

    # Build mapping: original_name -> api_name
    card_entries = []
    skipped = []
    for name in original_names:
        api_name = get_api_name(name)
        if api_name is None:
            skipped.append(name)
            continue
        card_entries.append((name, api_name))

    if skipped:
        print(f"  Skipping {len(skipped)} entries: {skipped}")

    # Deduplicate API names while preserving order
    unique_api_names = []
    seen_api = set()
    for _, api_name in card_entries:
        if api_name not in seen_api:
            seen_api.add(api_name)
            unique_api_names.append(api_name)

    print(f"\nFetching {len(unique_api_names)} unique card IDs from YGOProDeck API...")
    print(f"  Using batch size of {BATCH_SIZE}, will make ~{(len(unique_api_names) + BATCH_SIZE - 1) // BATCH_SIZE} requests")

    # Batch fetch
    api_name_to_id = {}
    failed_names = []

    for i in range(0, len(unique_api_names), BATCH_SIZE):
        batch = unique_api_names[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(unique_api_names) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"  Batch {batch_num}/{total_batches} ({len(batch)} cards)...", end="", flush=True)

        try:
            results = fetch_card_batch(batch)
            found = 0
            for name in batch:
                if name in results:
                    api_name_to_id[name] = results[name]
                    found += 1
                else:
                    failed_names.append(name)
            print(f" found {found}/{len(batch)}")
        except Exception as e:
            print(f" ERROR: {e}")
            failed_names.extend(batch)

        time.sleep(REQUEST_DELAY)

    # Retry failed names individually
    if failed_names:
        print(f"\n  Retrying {len(failed_names)} cards individually...")
        still_failed = []
        for name in failed_names:
            print(f"    Trying '{name}'...", end="", flush=True)
            card_id = fetch_single_card(name)
            if card_id is not None:
                api_name_to_id[name] = card_id
                print(f" OK (id={card_id})")
            else:
                still_failed.append(name)
                print(" FAILED")
            time.sleep(REQUEST_DELAY)

        if still_failed:
            print(f"\n  WARNING: Could not find IDs for {len(still_failed)} cards:")
            for name in still_failed:
                print(f"    - {name}")

    # Now build the output
    print(f"\nGenerating {OUTPUT_FILE}...")

    # Categorize cards by ban status
    forbidden = []      # 0
    limited = []        # 1
    semi_limited = []   # 2
    whitelist = []      # 3 (not on ban list)

    already_seen_ids = set()

    for original_name, api_name in card_entries:
        card_id = api_name_to_id.get(api_name)
        if card_id is None:
            print(f"  Skipping '{original_name}' - no ID found")
            continue

        # Avoid duplicate IDs (e.g., Dark Magician / Dark Magician (Arkana))
        if card_id in already_seen_ids:
            continue
        already_seen_ids.add(card_id)

        # Look up ban status using original name first, then api name
        ban_status = ban_list.get(original_name, ban_list.get(api_name, 3))

        entry = (card_id, ban_status, original_name)

        if ban_status == 0:
            forbidden.append(entry)
        elif ban_status == 1:
            limited.append(entry)
        elif ban_status == 2:
            semi_limited.append(entry)
        else:
            whitelist.append(entry)

    # Write the conf file
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("!Untitled Banlist\n")
        f.write("--StartDate 2006-09-01\n")
        f.write("--EndDate 2007-03-01\n")
        f.write("$whitelist\n")

        f.write("#forbidden\n")
        for card_id, status, name in sorted(forbidden, key=lambda x: x[2]):
            f.write(f"{card_id} {status} --{name}\n")

        f.write("#limited\n")
        for card_id, status, name in sorted(limited, key=lambda x: x[2]):
            f.write(f"{card_id} {status} --{name}\n")

        f.write("#semi-limited\n")
        for card_id, status, name in sorted(semi_limited, key=lambda x: x[2]):
            f.write(f"{card_id} {status} --{name}\n")

        f.write("#whitelist\n")
        for card_id, status, name in sorted(whitelist, key=lambda x: x[0]):
            f.write(f"{card_id} {status} --{name}\n")

    total = len(forbidden) + len(limited) + len(semi_limited) + len(whitelist)
    print(f"\nDone! Wrote {total} entries to {OUTPUT_FILE}")
    print(f"  Forbidden: {len(forbidden)}")
    print(f"  Limited: {len(limited)}")
    print(f"  Semi-Limited: {len(semi_limited)}")
    print(f"  Whitelist: {len(whitelist)}")


if __name__ == "__main__":
    main()
