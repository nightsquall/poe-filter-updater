from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

EXCHANGE_OVERVIEW_URL = "https://poe.ninja/poe2/api/economy/exchange/current/overview"
STASH_OVERVIEW_URL = "https://poe.ninja/poe2/api/economy/stash/current/item/overview"

CATEGORY_SPECS = {
    "Currency": {"endpoint": EXCHANGE_OVERVIEW_URL, "type": "Currency"},
    "Fragments": {"endpoint": EXCHANGE_OVERVIEW_URL, "type": "Fragments"},
    "Abyssal Bones": {"endpoint": EXCHANGE_OVERVIEW_URL, "type": "Abyss"},
    "Uncut Gems": {"endpoint": EXCHANGE_OVERVIEW_URL, "type": "UncutGems"},
    "Lineage Gems": {"endpoint": EXCHANGE_OVERVIEW_URL, "type": "LineageSupportGems"},
    "Essences": {"endpoint": EXCHANGE_OVERVIEW_URL, "type": "Essences"},
    "Soul Cores": {"endpoint": EXCHANGE_OVERVIEW_URL, "type": "SoulCores"},
    "Idols": {"endpoint": EXCHANGE_OVERVIEW_URL, "type": "Idols"},
    "Runes": {"endpoint": EXCHANGE_OVERVIEW_URL, "type": "Runes"},
    "Omens": {"endpoint": EXCHANGE_OVERVIEW_URL, "type": "Ritual"},
    "Expedition": {"endpoint": EXCHANGE_OVERVIEW_URL, "type": "Expedition"},
    "Liquid Emotions": {"endpoint": EXCHANGE_OVERVIEW_URL, "type": "Delirium"},
    "Catalysts": {"endpoint": EXCHANGE_OVERVIEW_URL, "type": "Breach"},
    "Verisium": {"endpoint": EXCHANGE_OVERVIEW_URL, "type": "Verisium"},
    "Unique Tablets": {"endpoint": STASH_OVERVIEW_URL, "type": "UniqueTablets"},
}


def fetch_overview(league: str, endpoint: str, item_type: str) -> dict:
    query = urlencode({"league": league, "type": item_type})
    request = Request(
        f"{endpoint}?{query}",
        headers={"User-Agent": "poe-filter-updater/0.1.0"},
    )

    with urlopen(request, timeout=30) as response:
        return json.load(response)


def slugify_category(item_type: str) -> str:
    return item_type.lower().replace(" ", "_")


def output_path_for_category(output_dir: Path, item_type: str) -> Path:
    return output_dir / f"{slugify_category(item_type)}_overview.json"
