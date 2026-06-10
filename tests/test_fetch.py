from pathlib import Path
from urllib.parse import urlencode

from poe_filter_updater.cli import build_output_filter, build_threshold_report, load_filter_first_match_states, render_override_section
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
            }
        ],
        filter_states={
            "Arcanist's Etcher": {
                "block": "Hide",
                "block_line": 10,
                "base_type_line": 11,
            }
        },
        min_value_ex=1.0,
        category_thresholds_ex={},
        ignored_items=set(),
    )

    assert report["summary"]["hidden_but_should_show"] == 1
    assert report["hidden_but_should_show"][0]["name"] == "Arcanist's Etcher"
    assert report["hidden_but_should_show"][0]["threshold_ex"] == 1.0


def test_threshold_report_uses_category_override_and_ignore_list() -> None:
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
            },
        ],
        filter_states={
            "Greater Resolve Rune": {
                "block": "Hide",
                "block_line": 10,
                "base_type_line": 11,
            },
            "Scroll of Wisdom": {
                "block": "Show",
                "block_line": 20,
                "base_type_line": 21,
            },
        },
        min_value_ex=1.0,
        category_thresholds_ex={"Runes": 0.5},
        ignored_items={"Scroll of Wisdom"},
    )

    assert report["summary"]["hidden_but_should_show"] == 1
    assert report["hidden_but_should_show"][0]["name"] == "Greater Resolve Rune"
    assert report["hidden_but_should_show"][0]["threshold_ex"] == 0.5
    assert report["summary"]["ignored_item_matches"] == 1
    assert report["ignored_item_matches"][0]["name"] == "Scroll of Wisdom"


def test_render_override_section_includes_show_and_hide_blocks() -> None:
    report = {
        "hidden_but_should_show": [{"name": "Arcanist's Etcher"}],
        "shown_but_should_hide": [{"name": "Scroll of Wisdom"}],
    }

    section = render_override_section(report)

    assert "AUTO-GENERATED OVERRIDES" in section
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
                "hidden_but_should_show": [{"name": "Arcanist's Etcher"}],
                "shown_but_should_hide": [],
            },
        )
    finally:
        filter_path.unlink(missing_ok=True)

    assert output.startswith("#===============================================================================================================")
    assert 'BaseType == "Arcanist\'s Etcher"' in output
    assert output.rstrip().endswith('BaseType "Gold"')
