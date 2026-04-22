#!/usr/bin/env python3
"""
Perego Cars Inventory Generator
================================
Scrapes AutoScout24 HCI listings and generates static HTML pages.

Usage:
    python3 scrape.py           # Full scrape + generate
    python3 scrape.py --force   # Regenerate even if no changes
"""
import sys
import os
import json
import logging
from datetime import datetime

# Ensure imports work from any working directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import OUTPUT_DIR, IMAGES_DIR, DETAIL_DIR, CACHE_FILE, LOG_DIR, CUSTOM_JSON, CUSTOM_IMAGES_DIR, SOLD_JSON
from fetcher import fetch_listings
from image_handler import download_images, cleanup_old_images
from html_generator import generate_grid_html, generate_detail_pages, generate_sold_detail_pages, format_chf


def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = os.path.join(LOG_DIR, "scrape.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def load_cache():
    """Load cached inventory from previous run."""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_cache(listings):
    """Save current inventory to cache."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(listings, f, ensure_ascii=False, indent=2, default=str)


def detect_changes(old_listings, new_listings):
    """Compare inventories. Returns (added, removed, price_changes)."""
    old_map = {item["id"]: item for item in old_listings}
    new_map = {item["id"]: item for item in new_listings}

    added = [new_map[lid] for lid in new_map if lid not in old_map]
    removed = [old_map[lid] for lid in old_map if lid not in new_map]

    price_changes = []
    for lid in new_map:
        if lid in old_map and new_map[lid]["price"] != old_map[lid]["price"]:
            price_changes.append({
                "listing": new_map[lid],
                "old_price": old_map[lid]["price"],
                "new_price": new_map[lid]["price"],
            })

    return added, removed, price_changes


def load_sold():
    """Load sold cars archive."""
    if os.path.exists(SOLD_JSON):
        with open(SOLD_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_sold(sold):
    """Save sold cars archive."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(SOLD_JSON, "w", encoding="utf-8") as f:
        json.dump(sold, f, ensure_ascii=False, indent=2, default=str)


def archive_removed(removed, sold):
    """Move removed listings to sold archive with date stamp."""
    sold_ids = {str(s.get("id")) for s in sold}
    for car in removed:
        if str(car.get("id")) not in sold_ids:
            car["sold_date"] = datetime.now().strftime("%Y-%m-%d")
            sold.append(car)
            sold_ids.add(str(car.get("id")))
    return sold


def remove_active_from_sold(sold, active_listings):
    """Remove cars from sold archive if they are currently active again."""
    active_ids = {str(car.get("id")) for car in active_listings}
    cleaned = [car for car in sold if str(car.get("id")) not in active_ids]
    removed_count = len(sold) - len(cleaned)
    return cleaned, removed_count


def print_summary(listings, added, removed, price_changes):
    """Print a human-readable summary."""
    print("\n" + "=" * 50)
    print(f"  PEREGO CARS — Inventaire {datetime.now().strftime('%d.%m.%Y')}")
    print("=" * 50)

    if added:
        for car in added:
            print(f"  + NOUVEAU : {car['make']} {car['model']} ({car['year']}) — {format_chf(car['price'])}")
    if removed:
        for car in removed:
            print(f"  - VENDU   : {car['make']} {car['model']} ({car['year']})")
    if price_changes:
        for pc in price_changes:
            car = pc["listing"]
            print(f"  ~ PRIX    : {car['make']} {car['model']} ({format_chf(pc['old_price'])} -> {format_chf(pc['new_price'])})")
    if not added and not removed and not price_changes:
        print("  Aucun changement detecte.")

    print(f"\n  Total : {len(listings)} vehicules en inventaire")
    print("=" * 50 + "\n")


def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("=" * 50)
    logger.info("Starting inventory scrape")

    force = "--force" in sys.argv

    # 1. Fetch listings
    print("Fetching listings from AutoScout24...")
    listings = fetch_listings()

    if not listings:
        print("ERROR: No listings found. Check logs for details.")
        logger.error("No listings found — aborting")
        sys.exit(1)

    print(f"Found {len(listings)} listings")

    # 2. Check for changes
    old_listings = load_cache()
    added, removed, price_changes = detect_changes(old_listings, listings)

    if not force and not added and not removed and not price_changes and old_listings:
        print_summary(listings, added, removed, price_changes)
        print("No changes — skipping regeneration. Use --force to regenerate anyway.")
        return

    print_summary(listings, added, removed, price_changes)

    # 3. Download images
    print("Downloading images...")
    os.makedirs(IMAGES_DIR, exist_ok=True)
    for listing in listings:
        listing["local_images"] = download_images(listing)
        count = len(listing["local_images"])
        if count:
            print(f"  {listing['make']} {listing['model']}: {count} images")

    # 4. Load custom data
    custom_data = {}
    if os.path.exists(CUSTOM_JSON):
        with open(CUSTOM_JSON, "r", encoding="utf-8") as f:
            custom_data = json.load(f)
        print(f"Loaded custom data for {len(custom_data)} cars")

    os.makedirs(CUSTOM_IMAGES_DIR, exist_ok=True)

    # 5. Archive sold cars, and self-heal stale sold entries.
    sold = load_sold()
    sold, restored_count = remove_active_from_sold(sold, listings)

    if restored_count:
        print(f"Removed {restored_count} active cars from sold archive")

    if removed:
        sold = archive_removed(removed, sold)
        print(f"Archived {len(removed)} sold cars (total sold: {len(sold)})")

    if restored_count or removed:
        save_sold(sold)

    # 6. Generate HTML
    print("Generating HTML pages...")
    os.makedirs(DETAIL_DIR, exist_ok=True)

    grid_html = generate_grid_html(listings)
    detail_pages = generate_detail_pages(listings, custom_data)

    # Generate sold detail pages (VENDU badge, no buy CTAs, cross-sell to active stock)
    sold_pages = generate_sold_detail_pages(sold, listings, custom_data)

    # 7. Write output
    grid_path = os.path.join(OUTPUT_DIR, "grid.html")
    with open(grid_path, "w", encoding="utf-8") as f:
        f.write(grid_html)

    for slug, html in detail_pages.items():
        detail_path = os.path.join(DETAIL_DIR, f"{slug}.html")
        with open(detail_path, "w", encoding="utf-8") as f:
            f.write(html)

    for slug, html in sold_pages.items():
        detail_path = os.path.join(DETAIL_DIR, f"{slug}.html")
        with open(detail_path, "w", encoding="utf-8") as f:
            f.write(html)

    # 8. Save cache
    save_cache(listings)

    # 9. Cleanup old images (don't clean sold car images)
    cleanup_old_images(listings)

    # 10. Done
    sold_count = len(sold_pages)
    print(f"\nOutput ready in: {OUTPUT_DIR}")
    print(f"  grid.html          — paste into HighLevel cars-for-sale page")
    print(f"  detail/*.html      — {len(detail_pages)} active + {sold_count} sold pages")
    print(f"  images/            — all car photos")
    logger.info(f"Done: 1 grid + {len(detail_pages)} detail + {sold_count} sold pages")


if __name__ == "__main__":
    main()
