#!/usr/bin/env python3
"""
Download all alt art cropped images for cards listed in a text file.

Looks up each card name in output/cardinfo.json, fetches every entry in
"card_images", downloads the cropped art (image_url_cropped) for each,
resizes to 100x100, and saves to cards/images_resized/{image_id}.jpg.

Images already present on disk are skipped.

Usage:
    python scripts/download_alt_arts.py <card_list.txt> [cardinfo.json]

Defaults:
    cardinfo.json -> <repo_root>/output/cardinfo.json
"""

import json
import sys
import time
import urllib.request
import urllib.error
from io import BytesIO
from pathlib import Path

from PIL import Image

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
OUTPUT_DIR = ROOT_DIR / "cards" / "images_resized"
REQUEST_DELAY = 0.15

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def load_card_names(path):
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def load_cardinfo(path):
    """Return dict of lowercase(name) -> card dict."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {card["name"].lower(): card for card in data["data"]}


def download_and_resize(url, dest_path):
    """Download image from url, resize to 100x100, save to dest_path."""
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    img = Image.open(BytesIO(raw)).convert("RGB")
    img = img.resize((100, 100), Image.LANCZOS)
    img.save(dest_path, "JPEG")


def main():
    if len(sys.argv) < 2:
        print("Usage: python download_alt_arts.py <card_list.txt> [cardinfo.json]")
        sys.exit(1)

    card_list_file = Path(sys.argv[1])
    cardinfo_file = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT_DIR / "output" / "cardinfo.json"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loading card names from {card_list_file}...")
    names = load_card_names(card_list_file)
    print(f"  {len(names)} names")

    print(f"Loading card data from {cardinfo_file}...")
    lookup = load_cardinfo(cardinfo_file)
    print(f"  {len(lookup)} cards in database")

    downloaded = 0
    skipped = 0
    not_found = []

    for name in names:
        card = lookup.get(name.lower())
        if card is None:
            not_found.append(name)
            continue

        images = card.get("card_images", [])
        print(f"{card['name']}  ({len(images)} art(s))")

        for img_entry in images:
            img_id = img_entry.get("id")
            url = img_entry.get("image_url_cropped")
            if not img_id or not url:
                continue

            dest = OUTPUT_DIR / f"{img_id}.jpg"
            if dest.exists():
                print(f"  SKIP  {img_id}.jpg")
                skipped += 1
                continue

            print(f"  -> {img_id}.jpg  {url}")
            try:
                download_and_resize(url, dest)
                downloaded += 1
            except Exception as e:
                print(f"     ERROR: {e}")

            time.sleep(REQUEST_DELAY)

    print(f"\nDone. Downloaded: {downloaded}  Skipped: {skipped}")
    if not_found:
        print(f"Not found in cardinfo ({len(not_found)}): {not_found}")


if __name__ == "__main__":
    main()
