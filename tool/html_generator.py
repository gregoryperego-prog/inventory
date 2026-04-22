"""
Perego Cars Inventory Tool — HTML Generator
Renders listing grid and detail pages from templates.
"""
import os
import re
import json
import logging
from datetime import datetime
from urllib.parse import quote

from config import (
    TEMPLATES_DIR, IMAGES_DIR, IMAGE_BASE_URL, WHATSAPP_NUMBER, SITE_URL,
    GITHUB_PAGES_URL, FUEL_TYPE_FR, TRANSMISSION_FR, BODY_TYPE_FR,
    CUSTOM_IMAGES_DIR, CUSTOM_IMAGES_URL, SOLD_IMAGES_URL,
)
from image_handler import make_slug

logger = logging.getLogger(__name__)


# ── Formatting Helpers ──

def format_chf(price):
    """Format price Swiss style: 235000 -> CHF 235'000.--"""
    if not price:
        return "Prix sur demande"
    s = str(int(price))
    groups = []
    while s:
        groups.append(s[-3:])
        s = s[:-3]
    formatted = "'".join(reversed(groups))
    return f"CHF {formatted}.--"


def format_km(mileage):
    """Format mileage Swiss style: 12000 -> 12'000"""
    if not mileage:
        return "0"
    s = str(int(mileage))
    groups = []
    while s:
        groups.append(s[-3:])
        s = s[:-3]
    return "'".join(reversed(groups))


def translate(value, mapping):
    """Translate an enum value using a mapping dict."""
    if not value:
        return ""
    # Try exact match, then lowercase, then return raw
    return mapping.get(value, mapping.get(value.lower(), value.replace("_", " ").title()))


def _read_template(name):
    """Read a template file from the templates directory."""
    path = os.path.join(TEMPLATES_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _render(template, context):
    """Simple template rendering: replace {{key}} with values."""
    result = template
    for key, value in context.items():
        result = result.replace("{{" + key + "}}", str(value))
    return result


# ── SEO Helpers ──

def _build_schema_json(listing, slug, is_sold=False):
    """Build Schema.org Vehicle JSON-LD for a detail page."""
    local_images = listing.get("local_images", [])
    image_base_url = SOLD_IMAGES_URL if is_sold else IMAGE_BASE_URL
    og_image = f"{image_base_url}/{local_images[0]}" if local_images else ""
    full_name = listing.get("full_name", f"{listing['make']} {listing.get('model', '')}")

    schema = {
        "@context": "https://schema.org",
        "@type": "Vehicle",
        "name": f"{listing['make']} {full_name}",
        "brand": {"@type": "Brand", "name": listing["make"]},
        "model": listing.get("model", ""),
        "vehicleModelDate": str(listing["year"]) if listing.get("year") else "",
        "mileageFromOdometer": {
            "@type": "QuantitativeValue",
            "value": listing.get("mileage", 0),
            "unitCode": "KMT",
        },
        "fuelType": translate(listing.get("fuel_type", ""), FUEL_TYPE_FR),
        "vehicleTransmission": translate(listing.get("transmission", ""), TRANSMISSION_FR),
        "bodyType": translate(listing.get("body_type", ""), BODY_TYPE_FR),
        "image": og_image,
        "url": f"{GITHUB_PAGES_URL}/detail/{slug}.html",
        "offers": {
            "@type": "Offer",
            "price": listing.get("price", 0),
            "priceCurrency": "CHF",
            "availability": "https://schema.org/SoldOut" if is_sold else "https://schema.org/InStock",
            "seller": {
                "@type": "AutoDealer",
                "name": "Perego Cars",
                "url": SITE_URL,
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": "Rte Suisse 2",
                    "addressLocality": "Etoy",
                    "postalCode": "1163",
                    "addressCountry": "CH",
                },
                "telephone": "+41218698911",
            },
        },
    }

    # Add horsepower if available
    if listing.get("horsepower"):
        schema["vehicleEngine"] = {
            "@type": "EngineSpecification",
            "enginePower": {
                "@type": "QuantitativeValue",
                "value": listing["horsepower"],
                "unitText": "ch",
            },
        }

    # Clean empty values
    if not schema["vehicleModelDate"]:
        del schema["vehicleModelDate"]
    if not schema["fuelType"]:
        del schema["fuelType"]
    if not schema["vehicleTransmission"]:
        del schema["vehicleTransmission"]
    if not schema["bodyType"]:
        del schema["bodyType"]

    return f'<script type="application/ld+json">\n    {json.dumps(schema, ensure_ascii=False, indent=4)}\n    </script>'


def _seo_context(listing, slug, is_sold=False):
    """Build SEO-specific context variables for a detail page."""
    local_images = listing.get("local_images", [])
    image_base_url = SOLD_IMAGES_URL if is_sold else IMAGE_BASE_URL
    og_image = f"{image_base_url}/{local_images[0]}" if local_images else ""
    canonical = f"{GITHUB_PAGES_URL}/detail/{slug}.html"
    seo_status = "Vendu" if is_sold else "En vente"

    return {
        "canonical_url": canonical,
        "og_image": og_image,
        "schema_json": _build_schema_json(listing, slug, is_sold),
        "seo_status": seo_status,
    }


# ── Grid Page ──

def _compute_tags(listing, top_price_ids):
    """Compute smart filter tags for a listing."""
    tags = []
    price = listing.get("price", 0)
    year = listing.get("year", 0)
    hp = listing.get("horsepower", 0)
    mileage = listing.get("mileage", 0)
    body = listing.get("body_type", "")
    teaser = (listing.get("teaser") or "").lower()

    if listing["id"] in top_price_ids:
        tags.append("expensive")
    if price and price < 60000:
        tags.append("deal")
    if hp and hp > 400:
        tags.append("powerful")
    if "1 of " in teaser or "limited" in teaser:
        tags.append("rare")
    if year and year < 1990:
        tags.append("classic")
    if mileage and mileage < 10000:
        tags.append("lowkm")
    if body == "cabriolet":
        tags.append("cabriolet")
    return ",".join(tags)


def generate_grid_html(listings):
    """Generate the full listing grid HTML block."""
    card_tpl = _read_template("car_card.html")
    grid_tpl = _read_template("grid_block.html")

    # Pre-compute top 5 most expensive IDs
    sorted_by_price = sorted(listings, key=lambda l: l.get("price", 0), reverse=True)
    top_price_ids = {l["id"] for l in sorted_by_price[:5]}

    cards_html = []
    for listing in listings:
        slug = make_slug(listing["make"], listing["model"], listing["id"])
        local_images = listing.get("local_images", [])
        thumb = f"{IMAGE_BASE_URL}/{local_images[0]}" if local_images else ""

        # Build display name: use full_name minus the make prefix for richer card titles
        full_name = listing.get("full_name", "")
        make = listing["make"]
        if full_name and full_name.upper().startswith(make.upper()):
            display_name = full_name[len(make):].strip()
        elif full_name:
            display_name = full_name
        else:
            display_name = listing["model"]
        if not display_name:
            display_name = listing["model"]

        tags = _compute_tags(listing, top_price_ids)

        card = _render(card_tpl, {
            "detail_url": f"{GITHUB_PAGES_URL}/detail/{slug}.html",
            "image_url": thumb,
            "make": listing["make"],
            "make_upper": listing["make"].upper(),
            "model": display_name,
            "model_lower": display_name.lower(),
            "year": listing["year"] if listing["year"] else "Neuf",
            "year_raw": str(listing["year"]) if listing["year"] else "0",
            "mileage_fmt": format_km(listing["mileage"]),
            "mileage_raw": str(listing["mileage"]) if listing["mileage"] else "0",
            "price_fmt": format_chf(listing["price"]),
            "price_raw": str(listing["price"]) if listing["price"] else "0",
            "hp_raw": str(listing["horsepower"]) if listing.get("horsepower") else "0",
            "body_type": listing.get("body_type", ""),
            "tags": tags,
        })
        cards_html.append(card)

    grid = _render(grid_tpl, {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "count": str(len(listings)),
        "car_cards": "\n".join(cards_html),
    })

    logger.info(f"Generated grid with {len(listings)} cards")
    return grid


def _display_name(listing):
    """Get display name: full_name minus make prefix, truncated to 35 chars."""
    full = listing.get("full_name", "")
    make = listing.get("make", "")
    if full and full.upper().startswith(make.upper()):
        name = full[len(make):].strip()
    else:
        name = full or listing.get("model", "")
    if not name:
        name = listing.get("model", "")
    if len(name) > 35:
        name = name[:32] + "..."
    return name


# ── YouTube Helper ──

def _extract_youtube_id(url):
    """Extract YouTube video ID from various URL formats."""
    match = re.search(r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})', url)
    return match.group(1) if match else None


# ── Cross-Selling ──

def _pick_related_cars(current, all_listings, max_count=4):
    """Pick related cars: same make first, then closest price. Never the current car."""
    candidates = [l for l in all_listings if l["id"] != current["id"]]
    if not candidates:
        return []

    make = current["make"].lower()
    price = current.get("price", 0) or 0

    # Score: same make = 1000 bonus, then closeness in price
    def score(l):
        same_make = 1000 if l["make"].lower() == make else 0
        price_diff = abs((l.get("price", 0) or 0) - price) if price else 0
        return same_make - price_diff / 1000  # Higher = better match

    candidates.sort(key=score, reverse=True)
    return candidates[:max_count]


# ── Teaser Cleanup ──

# Common English words/phrases that signal an English duplicate
_EN_MARKERS = re.compile(
    r'\b(swiss delivered|delivered|all services|very beautiful|new condition|'
    r'owner|worldwide|world wide|matching number|inside|outside|front and rear|'
    r'parking assistance|camera 360|navigation|bluetooth|privacy windows|'
    r'brake? caliper|bang & olufsen|without|made by|inch wheels|wheels\b|'
    r'\bgold\b|carbon\b|leather\b|seats\b|system\b|view\b|rear\b|front\b|'
    r'\bnew\b|condition\b|warranty\b|approved\b)\b',
    re.IGNORECASE,
)


def _filter_teaser_items(teaser_text):
    """Split teaser on common delimiters, remove English items, return clean FR text or empty."""
    # Split on | or spaced I or spaced - (common AutoScout24 separators)
    items = re.split(r'\s*\|\s*|\s+I\s+|\s+-\s+', teaser_text)
    items = [s.strip().rstrip('-').strip() for s in items if len(s.strip()) > 2]

    fr_items = []
    for item in items:
        if _EN_MARKERS.search(item):
            continue
        fr_items.append(item)

    if not fr_items:
        return ""  # All English — hide section entirely
    return " | ".join(fr_items)


# ── Sales Guru — "Pourquoi cette voiture" ──

def _compute_selling_points(listing, all_listings):
    """Auto-generate persuasive selling points from listing data."""
    points = []
    price = listing.get("price", 0) or 0
    mileage = listing.get("mileage", 0) or 0
    year = listing.get("year", 0) or 0
    hp = listing.get("horsepower", 0) or 0
    body = listing.get("body_type", "") or ""
    teaser = (listing.get("teaser") or "").lower()
    current_year = datetime.now().year

    # Compute fleet-wide stats for comparison
    prices = [l.get("price", 0) for l in all_listings if l.get("price")]
    avg_price = sum(prices) / len(prices) if prices else 0
    mileages = [l.get("mileage", 0) for l in all_listings if l.get("mileage")]
    avg_mileage = sum(mileages) / len(mileages) if mileages else 0
    hps = [l.get("horsepower", 0) for l in all_listings if l.get("horsepower")]
    avg_hp = sum(hps) / len(hps) if hps else 0

    # 1. Price positioning
    if price and avg_price and price < avg_price * 0.7:
        points.append(("deal", "Prix tres competitif", "En dessous de la moyenne de notre inventaire"))
    elif price and price > 500000:
        points.append(("trophy", "Piece de collection", "Un investissement dans l'excellence automobile"))

    # 2. Mileage insights
    if mileage and mileage < 1000:
        points.append(("sparkles", "Pratiquement neuf", f"Seulement {format_km(mileage)} km au compteur"))
    elif mileage and mileage < 10000:
        points.append(("gauge", "Tres faible kilometrage", f"{format_km(mileage)} km — usage soigne"))
    elif year and mileage and year < current_year:
        age = current_year - year
        if age > 0:
            km_per_year = mileage / age
            if km_per_year < 5000:
                points.append(("gauge", "Usage modere", f"Moyenne de {format_km(int(km_per_year))} km/an"))

    # 3. Performance
    if hp and hp > 600:
        points.append(("bolt", "Supercar", f"{hp} ch sous le capot"))
    elif hp and hp > 400:
        points.append(("bolt", "Haute performance", f"{hp} ch — sensations garanties"))

    # 4. Rarity / limited edition
    if "1 of " in teaser or "limited" in teaser:
        points.append(("gem", "Edition limitee", "Production restreinte — modele recherche"))

    # 5. Classic / vintage appeal
    if year and year < 1980:
        points.append(("clock", "Classique d'exception", f"Millesime {year} — un patrimoine automobile"))
    elif year and year < 1995:
        points.append(("clock", "Youngtimer recherche", f"Millesime {year} — cote en hausse"))

    # 6. Convertible / lifestyle
    if body == "cabriolet":
        points.append(("sun", "Plaisir a ciel ouvert", "Cabriolet — profitez de chaque rayon de soleil"))

    # 7. Swiss car
    if "suisse" in teaser or "swiss" in teaser:
        points.append(("shield", "Vehicule suisse", "Entretien et historique suisse"))

    # 8. Brand-new / unregistered
    if "neuf" in teaser or "13.20" in teaser or (mileage and mileage < 100):
        points.append(("star", "Neuf / non immatricule", "Vehicule sans premiere mise en circulation"))

    # 9. Full options / PPF
    if "full" in teaser and "ppf" in teaser.lower():
        points.append(("shield", "Protection PPF", "Film de protection carrosserie integrale"))

    return points[:5]  # Max 5 selling points


# ── Detail Pages ──

def generate_detail_pages(listings, custom_data=None):
    """Generate individual detail pages. Returns {slug: html} dict."""
    detail_tpl = _read_template("detail_page.html")
    pages = {}

    for listing in listings:
        slug = make_slug(listing["make"], listing["model"], listing["id"])
        local_images = listing.get("local_images", [])
        custom = custom_data.get(listing["id"], {}) if custom_data else {}

        # Main image
        main_img = f"{IMAGE_BASE_URL}/{local_images[0]}" if local_images else ""

        # Thumbnail images (all images including first, mark first as active)
        thumbs_html = ""
        for i, img_file in enumerate(local_images):
            cls = "pcd-thumb active" if i == 0 else "pcd-thumb"
            thumbs_html += f'            <img class="{cls}" src="{IMAGE_BASE_URL}/{img_file}" alt="{listing["make"]} {listing["model"]}" loading="lazy">\n'

        # Extra custom images
        if custom.get("extra_images"):
            for img_file in custom["extra_images"]:
                thumbs_html += f'            <img class="pcd-thumb" src="{CUSTOM_IMAGES_URL}/{img_file}" alt="{listing["make"]} {listing["model"]}" loading="lazy">\n'

        # Spec rows
        specs = []
        if listing["year"]:
            specs.append(("Annee", str(listing["year"])))
        if listing["mileage"]:
            specs.append(("Kilometrage", f"{format_km(listing['mileage'])} km"))
        if listing["horsepower"]:
            specs.append(("Puissance", f"{listing['horsepower']} ch"))
        if listing["fuel_type"]:
            specs.append(("Carburant", translate(listing["fuel_type"], FUEL_TYPE_FR)))
        if listing["transmission"]:
            specs.append(("Transmission", translate(listing["transmission"], TRANSMISSION_FR)))
        if listing["body_type"]:
            specs.append(("Carrosserie", translate(listing["body_type"], BODY_TYPE_FR)))

        spec_rows_html = ""
        for label, value in specs:
            spec_rows_html += f'            <div class="pcd-spec-row"><span class="pcd-spec-label">{label}</span><span class="pcd-spec-value">{value}</span></div>\n'

        # Custom description
        custom_desc_html = ""
        if custom.get("description"):
            custom_desc_html = f'<div class="pcd-description"><h2 class="pcd-specs-title">Description</h2><div class="pcd-desc-text">{custom["description"]}</div></div>'

        # Service history
        service_html = ""
        if custom.get("service_history"):
            rows = ""
            for entry in custom["service_history"]:
                rows += f'<tr><td class="pcd-sh-date">{entry["date"]}</td><td>{entry["description"]}</td></tr>'
            service_html = f'<div class="pcd-service"><h2 class="pcd-specs-title">Historique d\'entretien</h2><table class="pcd-sh-table"><thead><tr><th>Date</th><th>Description</th></tr></thead><tbody>{rows}</tbody></table></div>'

        # YouTube videos
        videos_html = ""
        if custom.get("youtube_videos"):
            embeds = ""
            for yt_url in custom["youtube_videos"]:
                video_id = _extract_youtube_id(yt_url)
                if video_id:
                    embeds += f'<div class="pcd-video-wrap"><iframe src="https://www.youtube.com/embed/{video_id}" allowfullscreen loading="lazy"></iframe></div>'
            if embeds:
                videos_html = f'<div class="pcd-videos"><h2 class="pcd-specs-title">Videos</h2>{embeds}</div>'

        # WhatsApp pre-filled message
        wa_msg = quote(
            f"Bonjour, je suis interesse(e) par votre {listing['make']} {listing['model']}"
            f" ({listing['year']}) a {format_chf(listing['price'])}. "
            f"Est-il toujours disponible ?"
        )

        # Teaser block — FR only, hidden if all English
        teaser_block = ""
        if listing.get("teaser"):
            clean_teaser = _filter_teaser_items(listing["teaser"])
            if clean_teaser:
                teaser_block = f'<div class="pcd-teaser"><div class="pcd-teaser-title">Points forts</div><div class="pcd-teaser-raw">{clean_teaser}</div></div>'

        # Sales Guru — "Pourquoi cette voiture"
        selling_points = _compute_selling_points(listing, listings)
        guru_html = ""
        if selling_points:
            icon_map = {
                "deal": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>',
                "trophy": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/><path d="M4 22h16"/><path d="M10 22V8a4 4 0 0 1 4 0v14"/><path d="M6 2h12v7a6 6 0 0 1-12 0V2z"/></svg>',
                "sparkles": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/></svg>',
                "gauge": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>',
                "bolt": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/></svg>',
                "gem": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 3h12l4 6-10 13L2 9z"/><path d="M2 9h20"/><path d="m10 3 2 6 2-6"/></svg>',
                "clock": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
                "sun": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>',
                "shield": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>',
                "star": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>',
                "chart": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>',
            }
            cards = ""
            for icon_key, title, desc in selling_points:
                icon_svg = icon_map.get(icon_key, icon_map["star"])
                cards += f'<div class="pcd-guru-card"><div class="pcd-guru-icon">{icon_svg}</div><div class="pcd-guru-text"><div class="pcd-guru-title">{title}</div><div class="pcd-guru-desc">{desc}</div></div></div>'
            guru_html = f'<div class="pcd-guru"><h2 class="pcd-specs-title">Pourquoi cette voiture</h2><div class="pcd-guru-grid">{cards}</div></div>'

        # Cross-sell — "Decouvrez aussi"
        related = _pick_related_cars(listing, listings)
        crosssell_html = ""
        if related:
            cards_cs = ""
            for rel in related:
                rel_slug = make_slug(rel["make"], rel["model"], rel["id"])
                rel_imgs = rel.get("local_images", [])
                rel_thumb = f"{IMAGE_BASE_URL}/{rel_imgs[0]}" if rel_imgs else ""
                rel_name = rel.get("full_name", f"{rel['make']} {rel['model']}")
                cards_cs += (
                    f'<a href="{GITHUB_PAGES_URL}/detail/{rel_slug}.html" class="pcd-cs-card">'
                    f'<img class="pcd-cs-img" src="{rel_thumb}" alt="{rel_name}" loading="lazy">'
                    f'<div class="pcd-cs-info">'
                    f'<div class="pcd-cs-brand">{rel["make"].upper()}</div>'
                    f'<div class="pcd-cs-name">{_display_name(rel)}</div>'
                    f'<div class="pcd-cs-price">{format_chf(rel.get("price"))}</div>'
                    f'</div></a>'
                )
            crosssell_html = f'<div class="pcd-crosssell"><h2 class="pcd-specs-title">Decouvrez aussi</h2><div class="pcd-cs-grid">{cards_cs}</div></div>'

        context = {
            "make": listing["make"],
            "make_upper": listing["make"].upper(),
            "model": listing["model"],
            "full_name": listing.get("full_name", f"{listing['make']} {listing['model']}"),
            "year": str(listing["year"]) if listing["year"] else "Neuf",
            "mileage_fmt": format_km(listing["mileage"]),
            "price_fmt": format_chf(listing["price"]),
            "price_raw": str(listing["price"]) if listing["price"] else "0",
            "main_image": main_img,
            "thumbnail_images": thumbs_html,
            "spec_rows": spec_rows_html,
            "custom_description": custom_desc_html,
            "service_history": service_html,
            "youtube_videos": videos_html,
            "whatsapp_number": WHATSAPP_NUMBER,
            "whatsapp_msg": wa_msg,
            "listing_url": listing["listing_url"],
            "grid_url": f"{SITE_URL}/cars-for-sale",
            "teaser_block": teaser_block,
            "sales_guru": guru_html,
            "crosssell": crosssell_html,
        }
        context.update(_seo_context(listing, slug, is_sold=False))

        page = _render(detail_tpl, context)
        pages[slug] = page

    logger.info(f"Generated {len(pages)} detail pages")
    return pages


# ── Sold Detail Pages ──

def generate_sold_detail_pages(sold_listings, active_listings, custom_data=None):
    """Generate detail pages for sold cars with VENDU badge + cross-sell to active stock."""
    if not sold_listings:
        return {}

    detail_tpl = _read_template("detail_page.html")
    pages = {}

    for listing in sold_listings:
        slug = make_slug(listing["make"], listing["model"], listing["id"])
        local_images = listing.get("local_images", [])
        custom = custom_data.get(listing["id"], {}) if custom_data else {}

        main_img = f"{SOLD_IMAGES_URL}/{local_images[0]}" if local_images else ""

        thumbs_html = ""
        for i, img_file in enumerate(local_images):
            cls = "pcd-thumb active" if i == 0 else "pcd-thumb"
            thumbs_html += f'            <img class="{cls}" src="{SOLD_IMAGES_URL}/{img_file}" alt="{listing["make"]} {listing["model"]}" loading="lazy">\n'

        # Extra custom images
        if custom.get("extra_images"):
            for img_file in custom["extra_images"]:
                thumbs_html += f'            <img class="pcd-thumb" src="{CUSTOM_IMAGES_URL}/{img_file}" alt="{listing["make"]} {listing["model"]}" loading="lazy">\n'

        # Spec rows (same as active)
        specs = []
        if listing.get("year"):
            specs.append(("Annee", str(listing["year"])))
        if listing.get("mileage"):
            specs.append(("Kilometrage", f"{format_km(listing['mileage'])} km"))
        if listing.get("horsepower"):
            specs.append(("Puissance", f"{listing['horsepower']} ch"))
        if listing.get("fuel_type"):
            specs.append(("Carburant", translate(listing["fuel_type"], FUEL_TYPE_FR)))
        if listing.get("transmission"):
            specs.append(("Transmission", translate(listing["transmission"], TRANSMISSION_FR)))
        if listing.get("body_type"):
            specs.append(("Carrosserie", translate(listing["body_type"], BODY_TYPE_FR)))
        spec_rows_html = ""
        for label, value in specs:
            spec_rows_html += f'            <div class="pcd-spec-row"><span class="pcd-spec-label">{label}</span><span class="pcd-spec-value">{value}</span></div>\n'

        # Custom description
        custom_desc_html = ""
        if custom.get("description"):
            custom_desc_html = f'<div class="pcd-description"><h2 class="pcd-specs-title">Description</h2><div class="pcd-desc-text">{custom["description"]}</div></div>'

        # YouTube videos
        videos_html = ""
        if custom.get("youtube_videos"):
            embeds = ""
            for yt_url in custom["youtube_videos"]:
                video_id = _extract_youtube_id(yt_url)
                if video_id:
                    embeds += f'<div class="pcd-video-wrap"><iframe src="https://www.youtube.com/embed/{video_id}" allowfullscreen loading="lazy"></iframe></div>'
            if embeds:
                videos_html = f'<div class="pcd-videos"><h2 class="pcd-specs-title">Videos</h2>{embeds}</div>'

        # Teaser (FR only, hidden if all English)
        teaser_block = ""
        if listing.get("teaser"):
            clean_teaser = _filter_teaser_items(listing["teaser"])
            if clean_teaser:
                teaser_block = f'<div class="pcd-teaser"><div class="pcd-teaser-title">Points forts</div><div class="pcd-teaser-raw">{clean_teaser}</div></div>'

        # Cross-sell → active stock only (the whole point for SEO)
        related = _pick_related_cars(listing, active_listings)
        crosssell_html = ""
        if related:
            cards_cs = ""
            for rel in related:
                rel_slug = make_slug(rel["make"], rel["model"], rel["id"])
                rel_imgs = rel.get("local_images", [])
                rel_thumb = f"{IMAGE_BASE_URL}/{rel_imgs[0]}" if rel_imgs else ""
                cards_cs += (
                    f'<a href="{GITHUB_PAGES_URL}/detail/{rel_slug}.html" class="pcd-cs-card">'
                    f'<img class="pcd-cs-img" src="{rel_thumb}" alt="{rel["make"]} {rel["model"]}" loading="lazy">'
                    f'<div class="pcd-cs-info">'
                    f'<div class="pcd-cs-brand">{rel["make"].upper()}</div>'
                    f'<div class="pcd-cs-name">{rel["model"]}</div>'
                    f'<div class="pcd-cs-price">{format_chf(rel.get("price"))}</div>'
                    f'</div></a>'
                )
            crosssell_html = f'<div class="pcd-crosssell"><h2 class="pcd-specs-title">Decouvrez notre stock</h2><div class="pcd-cs-grid">{cards_cs}</div></div>'

        # VENDU badge replaces leasing + CTAs via sold_overlay
        sold_date = listing.get("sold_date", "")
        sold_overlay = (
            f'<div style="background:#1A1A1A;color:#fff;padding:1rem;border-radius:0.75rem;text-align:center;margin-bottom:1rem;">'
            f'<div style="font-size:1.4rem;font-weight:700;letter-spacing:3px;">VENDU</div>'
            f'{"<div style=font-size:0.8rem;margin-top:0.3rem;opacity:0.7>" + sold_date + "</div>" if sold_date else ""}'
            f'</div>'
        )

        # WhatsApp message for similar cars
        wa_msg = quote(
            f"Bonjour, je recherche un vehicule similaire au {listing['make']} {listing['model']}"
            f" ({listing.get('year', '')}) que vous avez vendu. Avez-vous quelque chose de comparable ?"
        )

        context = {
            "make": listing["make"],
            "make_upper": listing["make"].upper(),
            "model": listing.get("model", ""),
            "full_name": listing.get("full_name", f"{listing['make']} {listing.get('model', '')}"),
            "year": str(listing["year"]) if listing.get("year") else "",
            "mileage_fmt": format_km(listing.get("mileage")),
            "price_fmt": format_chf(listing.get("price")),
            "price_raw": "0",  # Disable leasing calculator for sold cars
            "main_image": main_img,
            "thumbnail_images": thumbs_html,
            "spec_rows": spec_rows_html,
            "custom_description": custom_desc_html,
            "service_history": "",
            "youtube_videos": videos_html,
            "whatsapp_number": WHATSAPP_NUMBER,
            "whatsapp_msg": wa_msg,
            "listing_url": listing.get("listing_url", "#"),
            "grid_url": f"{SITE_URL}/cars-for-sale",
            "teaser_block": teaser_block,
            "sales_guru": sold_overlay,  # Replace guru with VENDU badge
            "crosssell": crosssell_html,
        }
        context.update(_seo_context(listing, slug, is_sold=True))

        page = _render(detail_tpl, context)
        pages[slug] = page

    logger.info(f"Generated {len(pages)} sold detail pages")
    return pages
