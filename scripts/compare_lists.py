"""
Compare two card list files and write the exclusive entries of each to separate output files.

Usage: python compare_lists.py
Compares output/chimeratech.txt with output/airblade_ocg.txt and writes:
  output/chimeratech_only.txt  - cards only in chimeratech.txt
  output/airblade_ocg_only.txt - cards only in airblade_ocg.txt
"""

import os
from pathlib import Path

SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = SCRIPT_DIR.parent
OUTPUT_DIR = ROOT_DIR / "output"

CHIMERATECH_FILE = OUTPUT_DIR / "reaper.txt"
AIRBLADE_FILE = OUTPUT_DIR / "victory_ocg.txt"
CHIMERATECH_ONLY_FILE = OUTPUT_DIR / "reaper_only.txt"
AIRBLADE_ONLY_FILE = OUTPUT_DIR / "victory_ocg_only.txt"


def load_card_list(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def main():
    chimeratech = load_card_list(CHIMERATECH_FILE)
    airblade = load_card_list(AIRBLADE_FILE)

    chimeratech_set = set(chimeratech)
    airblade_set = set(airblade)

    chimeratech_only = sorted(chimeratech_set - airblade_set)
    airblade_only = sorted(airblade_set - chimeratech_set)

    with open(CHIMERATECH_ONLY_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(chimeratech_only) + "\n" if chimeratech_only else "")

    with open(AIRBLADE_ONLY_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(airblade_only) + "\n" if airblade_only else "")

    print(f"chimeratech.txt:      {len(chimeratech)} cards")
    print(f"airblade_ocg.txt:     {len(airblade)} cards")
    print(f"Only in chimeratech:  {len(chimeratech_only)} -> {CHIMERATECH_ONLY_FILE}")
    print(f"Only in airblade_ocg: {len(airblade_only)} -> {AIRBLADE_ONLY_FILE}")


if __name__ == "__main__":
    main()
