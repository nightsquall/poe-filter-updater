from pathlib import Path
from urllib.parse import urlencode

from poe_filter_updater.cli import build_divine_style_report, build_output_filter, build_threshold_report, load_filter_blocks, load_filter_first_match_states, render_override_section
from poe_filter_updater.fetch import EXCHANGE_OVERVIEW_URL, STASH_OVERVIEW_URL, CATEGORY_SPECS, output_path_for_category


def test_overview_url_query_shape() -> None:
    query = urlencode({"league": "Runes of Aldur", "type": "Currency"})
    assert f"{EXCHANGE_OVERVIEW_URL}?{query}" == (
        "https://poe.ninja/poe2/api/economy/exchange/current/overview"
        "?league=Runes+of+Aldur&type=Currency"
    )


def test_unique_tablets_use_stash_endpoint() -> None:
    assert CATEGORY_SPECS["Unique Tablets"]["endpoint"] == STASH_OVERVIEW_URL
    assert CATEGORY_SPECS["Unique Tablets"]["type"] == "UniqueTablets"


def test_soul_cores_use_compact_type_name() -> None:
    assert CATEGORY_SPECS["Soul Cores"]["type"] == "SoulCores"


def test_output_path_uses_category_slug() -> None:
    output_path = output_path_for_category(Path("data/poe_ninja"), "Liquid Emotions")
    assert output_path == Path("data/poe_ninja/liquid_emotions_overview.json")


def test_first_match_filter_state_is_kept() -> None:
    filter_path = Path("/tmp/test.filter")
    filter_path.write_text(
        'Hide\n    BaseType "Arcanist\'s Etcher"\n\nShow\n    BaseType "Arcanist\'s Etcher"\n',
        encoding="utf-8",
    )
    try:
        states = load_filter_first_match_states(filter_path)
    finally:
        filter_path.unlink(missing_ok=True)

    assert states["Arcanist's Etcher"]["block"] == "Hide"
    assert states["Arcanist's Etcher"]["block_line"] == 1


def test_threshold_report_flags_hidden_high_value_item() -> None:
    filter_blocks = [
        {
            "block": "Hide",
            "block_line": 10,
            "base_type_line": 11,
            "names": ["Arcanist's Etcher"],
            "actions": [],
            "rarity_condition": None,
        }
    ]
    report = build_threshold_report(
        value_rows=[
            {
                "category": "Currency",
                "id": "etcher",
                "name": "Arcanist's Etcher",
                "primary_value": 0.008129,
                "primary_currency": "divine",
                "max_volume_currency": "exalted",
                "max_volume_rate": 0.9671,
                "value_ex": 1.034,
                "base_type": "Arcanist's Etcher",
                "match_key": "Arcanist's Etcher",
                "match_mode": "name",
                "rarity": None,
            }
        ],
        filter_blocks=filter_blocks,
        min_value_ex=1.0,
        category_thresholds_ex={},
        ignored_items=set(),
        always_show_unique_rings=False,
        unique_ring_base_types=set(),
    )

    assert report["summary"]["hidden_but_should_show"] == 1
    assert report["hidden_but_should_show"][0]["name"] == "Arcanist's Etcher"
    assert report["hidden_but_should_show"][0]["threshold_ex"] == 1.0


def test_threshold_report_uses_category_override_and_ignore_list() -> None:
    filter_blocks = [
        {
            "block": "Hide",
            "block_line": 10,
            "base_type_line": 11,
            "names": ["Greater Resolve Rune"],
            "actions": [],
            "rarity_condition": None,
        },
        {
            "block": "Show",
            "block_line": 20,
            "base_type_line": 21,
            "names": ["Scroll of Wisdom"],
            "actions": [],
            "rarity_condition": None,
        },
    ]
    report = build_threshold_report(
        value_rows=[
            {
                "category": "Runes",
                "id": "greater-resolve-rune",
                "name": "Greater Resolve Rune",
                "primary_value": 0.005185,
                "primary_currency": "divine",
                "max_volume_currency": "exalted",
                "max_volume_rate": 1.46,
                "value_ex": 0.6828645,
                "base_type": "Greater Resolve Rune",
                "match_key": "Greater Resolve Rune",
                "match_mode": "name",
                "rarity": None,
            },
            {
                "category": "Currency",
                "id": "wisdom",
                "name": "Scroll of Wisdom",
                "primary_value": 0.0001,
                "primary_currency": "divine",
                "max_volume_currency": "exalted",
                "max_volume_rate": 999,
                "value_ex": 0.01,
                "base_type": "Scroll of Wisdom",
                "match_key": "Scroll of Wisdom",
                "match_mode": "name",
                "rarity": None,
            },
        ],
        filter_blocks=filter_blocks,
        min_value_ex=1.0,
        category_thresholds_ex={"Runes": 0.5},
        ignored_items={"Scroll of Wisdom"},
        always_show_unique_rings=False,
        unique_ring_base_types=set(),
    )

    assert report["summary"]["hidden_but_should_show"] == 1
    assert report["hidden_but_should_show"][0]["name"] == "Greater Resolve Rune"
    assert report["hidden_but_should_show"][0]["threshold_ex"] == 0.5
    assert report["summary"]["ignored_item_matches"] == 1
    assert report["ignored_item_matches"][0]["name"] == "Scroll of Wisdom"


def test_divine_style_report_uses_white_background_plus_sound_rule() -> None:
    report = build_divine_style_report(
        value_rows=[
            {"category": "Currency", "id": "annul", "name": "Orb of Annulment", "value_ex": 60.0, "base_type": "Orb of Annulment", "match_key": "Orb of Annulment", "match_mode": "name", "rarity": None},
            {"category": "Currency", "id": "divine", "name": "Divine Orb", "value_ex": 120.0, "base_type": "Divine Orb", "match_key": "Divine Orb", "match_mode": "name", "rarity": None},
            {"category": "Fragments", "id": "key", "name": "Azmeri Reliquary Key", "value_ex": 5000.0, "base_type": "Azmeri Reliquary Key", "match_key": "Azmeri Reliquary Key", "match_mode": "name", "rarity": None},
        ],
        filter_blocks=[
            {
                "block": "Show",
                "block_line": 10,
                "base_type_line": 11,
                "names": ["Orb of Annulment"],
                "actions": (
                    "SetFontSize 45",
                    "SetBackgroundColor 245 105 90 255",
                    "PlayAlertSound 1 300",
                ),
                "rarity_condition": None,
            },
            {
                "block": "Show",
                "block_line": 20,
                "base_type_line": 21,
                "names": ["Divine Orb"],
                "actions": (
                    "SetBackgroundColor 255 255 255 255",
                    "PlayAlertSound 6 300",
                ),
                "rarity_condition": None,
            },
        ],
        ignored_items=set(),
        enabled=True,
    )

    assert report["summary"]["divine_style_candidates"] == 1
    assert report["divine_style_candidates"][0]["name"] == "Orb of Annulment"
    assert report["summary"]["divine_style_unmatched"] == 1
    assert report["divine_style_unmatched"][0]["name"] == "Azmeri Reliquary Key"


def test_unique_base_type_matching_respects_rarity_unique() -> None:
    filter_path = Path("/tmp/test-unique.filter")
    filter_path.write_text(
        'Hide\n    BaseType == "Utility Belt"\n\nShow\n    Rarity Unique\n    BaseType == "Utility Belt"\n',
        encoding="utf-8",
    )
    try:
        filter_blocks = load_filter_blocks(filter_path)
    finally:
        filter_path.unlink(missing_ok=True)

    report = build_threshold_report(
        value_rows=[
            {
                "category": "UniqueAccessories",
                "id": 1,
                "name": "Mageblood",
                "base_type": "Utility Belt",
                "match_key": "Utility Belt",
                "match_mode": "unique_base_type",
                "rarity": "Unique",
                "primary_value": 100.0,
                "primary_currency": "divine",
                "max_volume_currency": None,
                "max_volume_rate": None,
                "value_ex": 1000.0,
            }
        ],
        filter_blocks=filter_blocks,
        min_value_ex=1.0,
        category_thresholds_ex={"UniqueAccessories": 3.0},
        ignored_items=set(),
        always_show_unique_rings=False,
        unique_ring_base_types=set(),
    )

    assert report["summary"]["hidden_but_should_show"] == 0
    assert report["summary"]["unmatched_items"] == 0


def test_precursor_tablet_matching_uses_variant_rarity() -> None:
    filter_blocks = [
        {
            "block": "Hide",
            "block_line": 10,
            "base_type_line": 11,
            "names": ["Overseer Tablet"],
            "actions": [],
            "rarity_condition": ("=", "Unique"),
        },
        {
            "block": "Show",
            "block_line": 20,
            "base_type_line": 21,
            "names": ["Overseer Tablet"],
            "actions": [],
            "rarity_condition": ("=", "Normal"),
        },
    ]

    report = build_threshold_report(
        value_rows=[
            {
                "category": "PrecursorTablets",
                "id": 1,
                "name": "Overseer Tablet",
                "base_type": "Overseer Tablet",
                "match_key": "Overseer Tablet",
                "match_mode": "base_type_rarity",
                "rarity": "Normal",
                "primary_value": 1.0,
                "primary_currency": "divine",
                "max_volume_currency": None,
                "max_volume_rate": None,
                "value_ex": 100.0,
            }
        ],
        filter_blocks=filter_blocks,
        min_value_ex=1.0,
        category_thresholds_ex={"PrecursorTablets": 1.0},
        ignored_items=set(),
        always_show_unique_rings=False,
        unique_ring_base_types=set(),
    )

    assert report["summary"]["hidden_but_should_show"] == 0
    assert report["summary"]["unmatched_items"] == 0


def test_render_override_section_includes_show_and_hide_blocks() -> None:
    report = {
        "divine_style_candidates": [{"name": "Orb of Annulment"}],
        "hidden_but_should_show": [{"name": "Arcanist's Etcher"}],
        "shown_but_should_hide": [{"name": "Scroll of Wisdom"}],
        "always_shown_unique_rings": [{"match_key": "Gold Ring", "match_mode": "unique_base_type"}],
    }

    section = render_override_section(report)

    assert "AUTO-GENERATED OVERRIDES" in section
    assert 'BaseType == "Orb of Annulment"' in section
    assert 'BaseType == "Arcanist\'s Etcher"' in section
    assert "SetBackgroundColor 0 255 255 255" in section
    assert 'BaseType == "Scroll of Wisdom"' in section


def test_build_output_filter_prepends_override_section() -> None:
    filter_path = Path("/tmp/base.filter")
    filter_path.write_text("Show\n    BaseType \"Gold\"\n", encoding="utf-8")
    try:
        output = build_output_filter(
            filter_path,
            {
                "divine_style_candidates": [{"name": "Orb of Annulment"}],
                "hidden_but_should_show": [{"name": "Arcanist's Etcher"}],
                "shown_but_should_hide": [],
            },
        )
    finally:
        filter_path.unlink(missing_ok=True)

    assert output.startswith("#===============================================================================================================")
    assert 'BaseType == "Arcanist\'s Etcher"' in output
    assert output.rstrip().endswith('BaseType "Gold"')
