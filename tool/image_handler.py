"""
Perego Cars Inventory Tool — Image Handler
Downloads and manages car images locally.
"""
import os
import re
import logging
import urllib.request
from config import IMAGES_DIR, SOLD_IMAGES_DIR, MAX_IMAGES_PER_CAR, REQUEST_HEADERS

logger = logging.getLogger(__name__)


def make_slug(make, model, listing_id):
    """Generate URL-friendly slug: porsche-911-gt3-rs-12345"""
    text = f"{make} {model}".lower()
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return f"{slug}-{listing_id}"


def _download_listing_images(listing, target_dir):
    """Download listing images into target_dir and return local filenames."""
    os.makedirs(target_dir, exist_ok=True)
    slug = make_slug(listing["make"], listing["model"], listing["id"])
    images = listing.get("images", [])[:MAX_IMAGES_PER_CAR]
    local_files = []

    headers = dict(REQUEST_HEADERS)
    headers["Referer"] = "https://www.autoscout24.ch/"

    for i, image_url in enumerate(images):
        if not image_url:
            continue

        # Determine extension
        ext = "jpg"
        if ".webp" in image_url:
            ext = "webp"
        elif ".png" in image_url:
            ext = "png"

        filename = f"{slug}-{i + 1:02d}.{ext}"
        filepath = os.path.join(target_dir, filename)

        if os.path.exists(filepath):
            local_files.append(filename)
            continue

        try:
            req = urllib.request.Request(image_url, headers=headers)
            data = urllib.request.urlopen(req, timeout=15).read()
            with open(filepath, "wb") as f:
                f.write(data)
            local_files.append(filename)
            logger.info(f"  Downloaded: {filename}")
        except Exception as e:
            logger.warning(f"  Failed to download {image_url}: {e}")

    return local_files


def download_images(listing):
    """Download active listing images, return list of local filenames."""
    return _download_listing_images(listing, IMAGES_DIR)


def download_sold_images(listing):
    """Download sold listing images, return list of local filenames."""
    return _download_listing_images(listing, SOLD_IMAGES_DIR)


def cleanup_old_images(current_listings):
    """Remove images for listings no longer in inventory."""
    if not os.path.isdir(IMAGES_DIR):
        return

    # Build set of active image prefixes
    active_slugs = set()
    for listing in current_listings:
        slug = make_slug(listing["make"], listing["model"], listing["id"])
        active_slugs.add(slug)

    # Remove orphaned images
    removed = 0
    for filename in os.listdir(IMAGES_DIR):
        # Extract slug from filename (everything before the -NN.ext suffix)
        match = re.match(r"^(.+)-\d{2}\.\w+$", filename)
        if match:
            file_slug = match.group(1)
            if file_slug not in active_slugs:
                filepath = os.path.join(IMAGES_DIR, filename)
                os.remove(filepath)
                removed += 1
                logger.info(f"  Cleaned up: {filename}")

    if removed:
        logger.info(f"Removed {removed} old images")
