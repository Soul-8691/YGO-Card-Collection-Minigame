#!/usr/bin/env python3
"""
Script to download Yu-Gi-Oh! card images and JSON data from YGOPRODeck API.
Takes a text file with card names (one per line) as input.
"""

import os
import json
import sys
import requests
import time
from pathlib import Path
from PIL import Image

# API endpoint
API_BASE_URL = "https://db.ygoprodeck.com/api/v7/cardinfo.php"

# Rate limiting: 20 requests per second max
REQUEST_DELAY = 0.05  # 50ms between requests = 20 requests/second max

def create_directories():
    """Create necessary directories for storing cards."""
    Path("cards/images").mkdir(parents=True, exist_ok=True)
    Path("cards/images_resized").mkdir(parents=True, exist_ok=True)
    Path("cards/json").mkdir(parents=True, exist_ok=True)

def download_card_data(card_name):
    """
    Fetch card data from YGOPRODeck API.
    Returns the card data or None if not found.
    """
    try:
        # Use exact name search
        params = {"name": card_name}
        response = requests.get(API_BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if "data" in data and len(data["data"]) > 0:
            return data["data"][0]  # Return first match
        else:
            print(f"  ⚠️  No data found for: {card_name}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"  ❌ Error fetching data for {card_name}: {e}")
        return None

def download_card_image(card_id, image_url):
    """
    Download card image from YGOPRODeck.
    Returns True if successful, False otherwise.
    """
    try:
        image_path = Path(f"cards/images/{card_id}.jpg")
        
        # Skip if already downloaded
        if image_path.exists():
            return True
        
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()
        
        with open(image_path, "wb") as f:
            f.write(response.content)
        
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"  ❌ Error downloading image for card ID {card_id}: {e}")
        return False

def resize_card_image(card_id):
    """Resize a downloaded cropped image from 624x624 to 100x100 and save to cards/images_resized."""
    src = Path(f"cards/images/{card_id}.jpg")
    dst = Path(f"cards/images_resized/{card_id}.jpg")
    if dst.exists():
        return True
    try:
        with Image.open(src) as img:
            img = img.resize((100, 100), Image.LANCZOS)
            img.save(dst)
        return True
    except Exception as e:
        print(f"  ❌ Error resizing image for card ID {card_id}: {e}")
        return False


def save_card_json(card_data, card_name):
    """Save card JSON data to a file."""
    try:
        card_id = card_data.get("id")
        json_path = Path(f"cards/json/{card_id}.json")
        
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(card_data, f, indent=2, ensure_ascii=False)
        
        return True
    except Exception as e:
        print(f"  ❌ Error saving JSON for {card_name}: {e}")
        return False

def process_card_list(card_list_file):
    """
    Process a text file with card names (one per line).
    Downloads images and JSON for each card.
    """
    if not os.path.exists(card_list_file):
        print(f"❌ Error: File '{card_list_file}' not found!")
        return
    
    create_directories()
    
    # Read card names from file
    with open(card_list_file, "r", encoding="utf-8") as f:
        card_names = [line.strip() for line in f if line.strip()]
    
    print(f"📋 Found {len(card_names)} cards to process\n")
    
    downloaded = 0
    failed = 0
    
    for i, card_name in enumerate(card_names, 1):
        print(f"[{i}/{len(card_names)}] Processing: {card_name}")
        
        # Fetch card data
        card_data = download_card_data(card_name)
        time.sleep(REQUEST_DELAY)  # Rate limiting
        
        if card_data is None:
            failed += 1
            continue
        
        card_id = card_data.get("id")
        card_type = card_data.get("type", "Unknown")
        
        # Get image URL from card_images array
        image_url = None
        if "card_images" in card_data and len(card_data["card_images"]) > 0:
            image_url = card_data["card_images"][0].get("image_url_cropped")
        
        if not image_url:
            print(f"  ⚠️  No image URL found for: {card_name}")
            failed += 1
            continue
        
        # Download image
        if download_card_image(card_id, image_url):
            print(f"  ✅ Image downloaded: {card_id}.jpg")
        else:
            failed += 1
            continue

        # Resize image
        if resize_card_image(card_id):
            print(f"  ✅ Image resized: cards/images_resized/{card_id}.jpg")
        
        time.sleep(REQUEST_DELAY)  # Rate limiting
        
        # Save JSON
        if save_card_json(card_data, card_name):
            print(f"  ✅ JSON saved: {card_id}.json")
        
        downloaded += 1
        print(f"  📝 Type: {card_type}\n")
    
    print(f"\n{'='*50}")
    print(f"✅ Successfully downloaded: {downloaded}")
    print(f"❌ Failed: {failed}")
    print(f"{'='*50}")

def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python download_cards.py <card_list.txt>")
        print("\nExample:")
        print("  python download_cards.py card_lists/legend_of_blue_eyes_names.txt")
        sys.exit(1)
    
    card_list_file = sys.argv[1]
    process_card_list(card_list_file)

if __name__ == "__main__":
    main()
