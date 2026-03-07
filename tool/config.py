"""
Perego Cars Inventory Tool — Configuration
"""
import os

# ── AutoScout24 ──
HCI_CONFIG_ID = "2198"
SELLER_ID = "62273"  # Perego Cars Sarl
SEARCH_URL = f"https://www.autoscout24.ch/fr/hci/v2/{HCI_CONFIG_ID}/search"
SELLER_FILTER = "Etoy"  # Filter listings by seller city

# ── Perego Cars ──
WHATSAPP_NUMBER = "41798076339"
LANDLINE = "+41 21 869 89 11"
SITE_URL = "https://www.peregocars.com"

# ── GitHub Pages ──
# IMPORTANT: Update this after creating your GitHub repo
# Format: https://<username>.github.io/<repo-name>
GITHUB_PAGES_URL = "https://peregocars.github.io/inventory"

# ── Paths ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)  # github-deploy root
OUTPUT_DIR = os.path.join(ROOT_DIR, "docs")  # GitHub Pages serves from /docs
IMAGES_DIR = os.path.join(OUTPUT_DIR, "images")
DETAIL_DIR = os.path.join(OUTPUT_DIR, "detail")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
CACHE_FILE = os.path.join(OUTPUT_DIR, "inventory.json")
LOG_DIR = os.path.join(BASE_DIR, "logs")

# ── Image Settings ──
MAX_IMAGES_PER_CAR = 10
IMAGE_BASE_URL = f"{GITHUB_PAGES_URL}/images"  # Public URL for images

# ── Custom Data ──
CUSTOM_JSON = os.path.join(ROOT_DIR, "..", "custom.json")  # Bridge writes here
CUSTOM_IMAGES_DIR = os.path.join(OUTPUT_DIR, "custom-images")
CUSTOM_IMAGES_URL = f"{GITHUB_PAGES_URL}/custom-images"

# ── Translations (FR) ──
FUEL_TYPE_FR = {
    "gasoline": "Essence",
    "petrol": "Essence",
    "diesel": "Diesel",
    "electric": "Electrique",
    "hybrid": "Hybride",
    "hybrid_petrol": "Hybride essence",
    "hybrid-petrol": "Hybride essence",
    "plugIn_hybrid_petrol": "Hybride rechargeable",
    "natural_gas": "Gaz naturel",
    "hydrogen": "Hydrogene",
    "lpg": "GPL",
    "ethanol": "Ethanol",
}

TRANSMISSION_FR = {
    "manual_gear": "Manuelle",
    "automatic_gear": "Automatique",
    "semi_automatic_gear": "Semi-automatique",
    "manual": "Manuelle",
    "automatic": "Automatique",
    "semi-automatic": "Semi-automatique",
}

BODY_TYPE_FR = {
    "sedan": "Berline",
    "coupe": "Coupe",
    "convertible": "Cabriolet",
    "suv": "SUV",
    "wagon": "Break",
    "hatchback": "Compacte",
    "van": "Fourgon",
    "pickup": "Pick-up",
    "limousine": "Limousine",
    "roadster": "Roadster",
    "sports_car": "Voiture de sport",
    "small_car": "Citadine",
}

# ── HTTP Headers ──
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-CH,fr;q=0.9,en;q=0.5",
}
