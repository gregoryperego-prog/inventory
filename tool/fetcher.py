"""
Perego Cars Inventory Tool — AutoScout24 Fetcher
Scrapes the HCI search page and extracts listing data from RSC payload.
"""
import urllib.request
import json
import re
import logging
from config import SEARCH_URL, SELLER_FILTER, REQUEST_HEADERS

logger = logging.getLogger(__name__)


def fetch_listings():
    """Fetch all Perego Cars listings from AutoScout24 HCI search page."""
    all_raw_listings = []
    seen_ids = set()
    max_pages = 10  # Safety limit

    for page_num in range(max_pages):
        # Page 0 = default URL, Page 1+ = ?page=N
        if page_num == 0:
            url = SEARCH_URL
        else:
            url = f"{SEARCH_URL}?page={page_num}"

        logger.info(f"Fetching page {page_num + 1}: {url}")

        req = urllib.request.Request(url, headers=REQUEST_HEADERS)
        response = urllib.request.urlopen(req, timeout=30)
        html = response.read().decode("utf-8")

        logger.info(f"Page {page_num + 1} fetched: {len(html)} bytes")

        # Extract from Next.js RSC streaming payload
        raw_listings = _extract_from_rsc_payload(html)

        if not raw_listings:
            # Fallback: extract from rendered HTML alt texts + image URLs
            raw_listings = _extract_from_html(html)

        if not raw_listings:
            logger.info(f"No more listings found on page {page_num + 1}, stopping.")
            break

        # Deduplicate by listing ID
        new_count = 0
        for raw in raw_listings:
            lid = str(raw.get("as24Id", raw.get("id", raw.get("listingId", ""))))
            if lid and lid not in seen_ids:
                seen_ids.add(lid)
                all_raw_listings.append(raw)
                new_count += 1

        logger.info(f"Page {page_num + 1}: {new_count} new listings (total so far: {len(all_raw_listings)})")

        # Check if there are more pages (look for pagination link)
        if f'page={page_num + 1}' not in html and page_num > 0:
            logger.info("No next page link found, stopping.")
            break

        # If this page returned no new results, stop
        if new_count == 0:
            break

    if not all_raw_listings:
        logger.error("Could not extract listings from any page")
        return []

    # Normalize
    listings = []
    for raw in all_raw_listings:
        car = _normalize_listing(raw)
        if car:
            listings.append(car)

    # Keep AutoScout24's natural order (newest listings first)

    logger.info(f"Extracted {len(listings)} listings total")
    return listings


def _extract_from_rsc_payload(html):
    """Extract listing objects from Next.js RSC streaming data."""
    # Get all __next_f.push payloads
    pushes = re.findall(
        r'self\.__next_f\.push\(\[(\d+),"(.*?)"\]\)', html, re.DOTALL
    )
    if not pushes:
        logger.warning("No __next_f push calls found")
        return []

    # Concatenate all payloads
    full = ""
    for _num, payload in pushes:
        full += payload

    # Unescape the doubly-escaped JSON
    unescaped = full.replace('\\"', '"').replace('\\\\', '\\').replace('\\n', '\n')

    # Find all listing objects by searching for the price/make/model pattern
    # Each listing has: "price":XXXXX followed by nearby "make":{"name":"..."} etc.
    # Strategy: find all JSON-like objects that contain seller info for Perego Cars
    listings = []

    # Find each listing by locating "price":NNNNN patterns and extracting the surrounding object
    price_positions = [m.start() for m in re.finditer(r'"price":\d+', unescaped)]

    for pos in price_positions:
        # Walk backwards to find the start of this object (look for opening patterns)
        # The listing starts with something like {"bodyType":... or {"as24Id":...
        search_start = max(0, pos - 3000)
        chunk = unescaped[search_start:pos + 500]

        # Try to extract a complete JSON object containing this price
        listing = _extract_listing_object(chunk, unescaped, pos)
        if listing and "seller" in listing:
            # Verify it's a Perego Cars listing
            seller = listing.get("seller", {})
            if isinstance(seller, dict) and SELLER_FILTER.lower() in seller.get("city", "").lower():
                listings.append(listing)

    if listings:
        logger.info(f"Found {len(listings)} listings from RSC payload")

    return listings


def _extract_listing_object(chunk, full_text, price_pos):
    """Try to extract a complete listing JSON object from the RSC data."""
    # The RSC format has listings as individual objects in an array
    # Find the boundaries by looking for the pattern of listing fields

    # Look for key fields that mark listing boundaries
    # Each listing typically starts with fields like "as24Id", "bodyType", etc.
    # and contains "make", "model", "price", "seller"

    # Find a reasonable start — look for {"as24Id" or {"bodyType" or first { before common fields
    search_start = max(0, price_pos - 3000)
    search_chunk = full_text[search_start:price_pos + 1000]

    # Find all opening braces and try to parse from each
    # Work backwards from the price to find the object start
    brace_positions = [i for i, c in enumerate(search_chunk) if c == '{']

    for brace_pos in reversed(brace_positions):
        # Only try positions that are before the price
        abs_pos = search_start + brace_pos
        if abs_pos >= price_pos:
            continue

        # Try to extract balanced JSON from this position
        test_str = full_text[abs_pos:]
        obj = _try_parse_json_object(test_str)
        if obj and isinstance(obj, dict):
            # Check if this looks like a car listing
            if "price" in obj and ("make" in obj or "seller" in obj):
                return obj

    return None


def _try_parse_json_object(text):
    """Try to parse a JSON object from the beginning of text."""
    # Find the matching closing brace
    depth = 0
    in_string = False
    escape = False

    for i, c in enumerate(text):
        if i > 10000:  # Safety limit
            break

        if escape:
            escape = False
            continue
        if c == '\\':
            escape = True
            continue
        if c == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                candidate = text[:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    # Clean control characters (newlines in teaser text etc.)
                    cleaned = re.sub(r'[\x00-\x1f]', ' ', candidate)
                    try:
                        return json.loads(cleaned)
                    except json.JSONDecodeError:
                        return None
    return None


def _extract_from_html(html):
    """Fallback: Extract basic listing data from rendered HTML."""
    logger.info("Using HTML fallback extraction")
    listings = []

    # Extract car names from img alt texts
    alts = re.findall(r'alt="([A-Z][A-Z\s]+ [^"]+?)"', html)

    # Extract listing IDs from image URLs
    img_pattern = r'images\.autoscout24\.ch/public/listing/\d+/(\d+)/(\d+)\.jpg'
    img_matches = re.findall(img_pattern, html)

    # Group images by listing ID
    listing_images = {}
    for listing_id, image_id in img_matches:
        if listing_id not in listing_images:
            listing_images[listing_id] = []
        img_url = f"https://images.autoscout24.ch/public/listing/{listing_id[:3]}/{listing_id}/{image_id}.jpg?w=768"
        if img_url not in listing_images[listing_id]:
            listing_images[listing_id].append(img_url)

    # Match alts to listing IDs (they appear in the same order)
    listing_ids = list(dict.fromkeys(
        re.findall(r'images\.autoscout24\.ch/public/listing/\d+/(\d+)/', html)
    ))

    for i, listing_id in enumerate(listing_ids):
        if i >= len(alts):
            break

        alt = alts[i]
        # Parse "PORSCHE Macan GTS PDK" -> make="PORSCHE", model="Macan GTS PDK"
        parts = alt.split(" ", 1)
        make = parts[0] if parts else ""
        model = parts[1] if len(parts) > 1 else ""

        listings.append({
            "id": listing_id,
            "make": make.title(),
            "model": model,
            "price": 0,  # Can't reliably extract from HTML
            "mileage": 0,
            "year": 0,
            "horsepower": 0,
            "fuel_type": "",
            "transmission": "",
            "body_type": "",
            "images": listing_images.get(listing_id, []),
            "listing_url": f"https://www.autoscout24.ch/fr/d/{listing_id}",
            "teaser": "",
        })

    logger.info(f"HTML fallback found {len(listings)} listings")
    return listings


def _normalize_listing(raw):
    """Convert raw AutoScout24 data to a clean car dict."""
    try:
        listing_id = str(
            raw.get("as24Id", raw.get("id", raw.get("listingId", "")))
        )

        # Handle make as object {"name":"PORSCHE","key":"porsche"} or string
        make_raw = raw.get("make", "")
        if isinstance(make_raw, dict):
            make = make_raw.get("name", "").title()
        else:
            make = str(make_raw).title()

        # Handle model as object or string
        model_raw = raw.get("model", "")
        if isinstance(model_raw, dict):
            model = model_raw.get("name", "")
        else:
            model = str(model_raw)

        # If model is empty, try to extract from versionFullName
        if not model or model == "None":
            full = raw.get("versionFullName", "")
            if full:
                # Remove make prefix if present
                if full.upper().startswith(make.upper()):
                    model = full[len(make):].strip()
                else:
                    model = full
            if not model or model == "None":
                model = ""

        if not listing_id or not make:
            return None

        # Price
        price = raw.get("price", 0)
        if isinstance(price, dict):
            price = price.get("value", 0)

        # Mileage
        mileage = raw.get("mileage", 0)
        if isinstance(mileage, dict):
            mileage = mileage.get("value", 0)

        # Year
        year = raw.get("firstRegistrationYear", raw.get("year", 0))

        # Fuel type
        fuel = raw.get("fuelType", "")
        if isinstance(fuel, dict):
            fuel = fuel.get("key", "")

        # Transmission
        trans = raw.get("transmissionType", "")
        if isinstance(trans, dict):
            trans = trans.get("key", "")

        # Body type
        body = raw.get("bodyType", "")
        if isinstance(body, dict):
            body = body.get("key", "")

        # Images
        images = []
        raw_images = raw.get("images", [])
        if isinstance(raw_images, list):
            for img in raw_images:
                if isinstance(img, dict):
                    url = img.get("url", img.get("uri", img.get("src", "")))
                    if url:
                        # Use a good resolution
                        if "?" not in url:
                            url += "?w=768"
                        images.append(url)
                elif isinstance(img, str):
                    images.append(img)

        # Full name / version
        full_name = raw.get("versionFullName", raw.get("title", ""))
        if not full_name:
            full_name = f"{make} {model}"

        return {
            "id": listing_id,
            "make": make,
            "model": model,
            "full_name": full_name,
            "price": int(price) if price else 0,
            "mileage": int(mileage) if mileage else 0,
            "year": int(year) if year else 0,
            "horsepower": int(raw.get("horsePower", raw.get("hp", 0)) or 0),
            "fuel_type": fuel,
            "transmission": trans,
            "body_type": body,
            "images": images,
            "listing_url": f"https://www.autoscout24.ch/fr/d/{listing_id}",
            "teaser": raw.get("teaser", ""),
        }
    except Exception as e:
        logger.warning(f"Failed to normalize listing: {e}")
        return None
