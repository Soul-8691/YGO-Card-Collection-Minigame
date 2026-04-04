#!/usr/bin/env python3
"""
Scrape tournament meta decks from ygoprodeck.com and save as .ydk files.

Iterates pages of https://ygoprodeck.com/category/format/tournament%20meta%20decks,
follows each deck link, extracts the embedded card-ID arrays, and writes a
standard .ydk file to output/decks/ygoprodeck/.

Requires: requests, beautifulsoup4  (pip install requests beautifulsoup4)
"""

import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR.parent / "output" / "decks" / "ygoprodeck"

BASE_URL = "https://ygoprodeck.com"
CATEGORY_URL = f"{BASE_URL}/category/format/tournament%20meta%20decks"
REQUEST_DELAY = 1.0  # seconds between requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Matches:  var maindeckjs = '[...]';
_DECK_ARRAY_RE = re.compile(
    r"var\s+(maindeckjs|extradeckjs|sidedeckjs)\s*=\s*'(\[.*?\])';",
    re.DOTALL,
)
_DECKNAME_RE = re.compile(r'var\s+deckname\s*=\s*"([^"]+)";')
_DECKID_RE = re.compile(r"/deck/[^/]+-(\d+)$")


def safe_filename(name):
    return re.sub(r'[<>:"/\\|?*\r\n]', "-", name).strip()


def get_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def fetch_deck_links_from_page(session, page_num):
    """Return list of absolute deck URLs from one listing page."""
    url = CATEGORY_URL if page_num == 1 else f"{CATEGORY_URL}?page={page_num}"
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    links = []
    for a in soup.select("a.deck_article-card-title, a.stretched-link"):
        href = a.get("href", "")
        if "/deck/" in href:
            full = href if href.startswith("http") else BASE_URL + href
            if full not in links:
                links.append(full)
    return links


def fetch_all_deck_links(session):
    """Paginate through all listing pages and collect every deck URL."""
    all_links = []
    page = 1
    while True:
        print(f"  Fetching listing page {page}...", end="", flush=True)
        links = fetch_deck_links_from_page(session, page)
        if not links:
            print(" no decks found, stopping.")
            break
        print(f" {len(links)} decks")
        # Avoid adding duplicates across pages
        for link in links:
            if link not in all_links:
                all_links.append(link)
        page += 1
        time.sleep(REQUEST_DELAY)
    return all_links


def parse_deck_page(html):
    """
    Extract deck name and card-ID arrays from a deck page's HTML.
    Returns (deckname, main_ids, extra_ids, side_ids) or None on failure.
    """
    arrays = {}
    for m in _DECK_ARRAY_RE.finditer(html):
        var_name = m.group(1)
        try:
            arrays[var_name] = json.loads(m.group(2))
        except json.JSONDecodeError:
            arrays[var_name] = []

    m = _DECKNAME_RE.search(html)
    if not m:
        return None
    deckname = m.group(1)

    return (
        deckname,
        arrays.get("maindeckjs", []),
        arrays.get("extradeckjs", []),
        arrays.get("sidedeckjs", []),
    )


def build_ydk(main_ids, extra_ids, side_ids):
    """Assemble a .ydk file string from three card-ID lists."""
    lines = ["#main"]
    lines.extend(str(i) for i in main_ids)
    lines.append("#extra")
    lines.extend(str(i) for i in extra_ids)
    lines.append("!side")
    lines.extend(str(i) for i in side_ids)
    return "\r\n".join(lines) + "\r\n"


def deck_id_from_url(url):
    m = _DECKID_RE.search(url)
    return m.group(1) if m else None


def download_deck(session, deck_url, output_dir):
    """Fetch a deck page, parse it, and write the .ydk file. Returns filename or None."""
    resp = session.get(deck_url, timeout=30)
    resp.raise_for_status()

    result = parse_deck_page(resp.text)
    if not result:
        return None

    deckname, main_ids, extra_ids, side_ids = result
    deck_id = deck_id_from_url(deck_url) or "unknown"
    filename = f"{safe_filename(deckname)}_{deck_id}.ydk"
    out_path = output_dir / filename

    ydk_content = build_ydk(main_ids, extra_ids, side_ids)
    out_path.write_text(ydk_content, encoding="utf-8")
    return filename


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    session = get_session()

    print("Collecting deck links from tournament meta decks...")
    deck_urls = fetch_all_deck_links(session)
    print(f"Found {len(deck_urls)} deck(s) total.\n")

    downloaded = 0
    skipped = 0
    failed = 0

    for i, url in enumerate(deck_urls, 1):
        deck_id = deck_id_from_url(url) or url

        # Skip if a file with this deck ID already exists
        existing = list(OUTPUT_DIR.glob(f"*_{deck_id}.ydk"))
        if existing:
            print(f"[{i}/{len(deck_urls)}] SKIP  {existing[0].name}")
            skipped += 1
            continue

        print(f"[{i}/{len(deck_urls)}] {url}...", end="", flush=True)
        try:
            filename = download_deck(session, url, OUTPUT_DIR)
            if filename:
                print(f"  -> {filename}")
                downloaded += 1
            else:
                print("  parse failed")
                failed += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1

        time.sleep(REQUEST_DELAY)

    print(f"\nDone. Downloaded: {downloaded}  Skipped: {skipped}  Failed: {failed}")


if __name__ == "__main__":
    main()
