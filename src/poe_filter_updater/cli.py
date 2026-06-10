from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from poe_filter_updater.fetch import CATEGORY_SPECS, fetch_overview, output_path_for_category


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch current poe.ninja PoE 2 economy data and compare it against a filter."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.json"),
        help="Path to the JSON config file.",
    )
    return parser.parse_args()


def load_config(config_path: Path) -> dict:
    with config_path.open("r", encoding="utf-8") as config_file:
        return json.load(config_file)


def save_json(output_path: Path, payload: object) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(payload, output_file, indent=2, sort_keys=True)
        output_file.write("\n")


def write_text(output_path: Path, content: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        output_file.write(content)


def fetch_category_snapshots(league: str, categories: list[str], output_dir: Path) -> dict[str, dict]:
    snapshots: dict[str, dict] = {}
    for category in categories:
        spec = CATEGORY_SPECS[category]
        payload = fetch_overview(league, spec["endpoint"], spec["type"])
        save_json(output_path_for_category(output_dir, category), payload)
        snapshots[category] = payload
    return snapshots


def load_filter_first_match_states(filter_path: Path) -> dict[str, dict[str, int | str]]:
    states: dict[str, dict[str, int | str]] = {}
    current_block: tuple[str, int] | None = None

    with filter_path.open("r", encoding="utf-8", errors="replace") as filter_file:
        for line_number, raw_line in enumerate(filter_file, start=1):
            line = raw_line.strip()
            if line.startswith("Show"):
                current_block = ("Show", line_number)
            elif line.startswith("Hide"):
                current_block = ("Hide", line_number)
            elif line.startswith("Minimal"):
                current_block = ("Minimal", line_number)

            if "BaseType" not in line or current_block is None:
                continue

            for name in re.findall(r'"([^"]+)"', line):
                states.setdefault(
                    name,
                    {
                        "block": current_block[0],
                        "block_line": current_block[1],
                        "base_type_line": line_number,
                    },
                )

    return states


def exalt_value_by_primary_currency(currency_snapshot: dict) -> dict[str, float]:
    currency_core = currency_snapshot["core"]
    primary_currency = currency_core["primary"]
    exalted_per_primary = currency_core["rates"]["exalted"]
    values = {
        primary_currency: exalted_per_primary,
        "exalted": 1.0,
    }

    for currency_name, rate_in_primary in currency_core["rates"].items():
        values[currency_name] = exalted_per_primary / rate_in_primary

    return values


def build_value_rows(snapshots: dict[str, dict]) -> list[dict]:
    rows: list[dict] = []
    seen_names: set[str] = set()
    primary_currency_values = exalt_value_by_primary_currency(snapshots["Currency"])

    for category, payload in snapshots.items():
        primary_currency = payload["core"]["primary"]
        ex_per_primary = primary_currency_values.get(primary_currency)
        if ex_per_primary is None:
            raise KeyError(f"No exalt conversion available for primary currency '{primary_currency}'")

        item_names = {item["id"]: item["name"] for item in payload.get("items", [])}

        for line in payload.get("lines", []):
            item_id = line["id"]
            name = item_names.get(item_id)
            if name is None or name in seen_names:
                continue

            primary_value = line["primaryValue"]
            value_ex = primary_value * ex_per_primary
            rows.append(
                {
                    "category": category,
                    "id": item_id,
                    "name": name,
                    "primary_value": primary_value,
                    "primary_currency": primary_currency,
                    "max_volume_currency": line["maxVolumeCurrency"],
                    "max_volume_rate": line["maxVolumeRate"],
                    "value_ex": value_ex,
                }
            )
            seen_names.add(name)

    rows.sort(key=lambda row: row["value_ex"], reverse=True)
    return rows


def build_threshold_report(
    value_rows: list[dict],
    filter_states: dict[str, dict[str, int | str]],
    min_value_ex: float,
    category_thresholds_ex: dict[str, float],
    ignored_items: set[str],
) -> dict:
    shown_but_should_hide: list[dict] = []
    hidden_but_should_show: list[dict] = []
    unmatched_items: list[dict] = []
    ignored_item_matches: list[dict] = []

    for row in value_rows:
        threshold_ex = category_thresholds_ex.get(row["category"], min_value_ex)

        if row["name"] in ignored_items:
            ignored_item_matches.append({**row, "threshold_ex": threshold_ex})
            continue

        filter_state = filter_states.get(row["name"])
        if filter_state is None:
            unmatched_items.append({**row, "threshold_ex": threshold_ex})
            continue

        report_row = {
            **row,
            "threshold_ex": threshold_ex,
            "filter_block": filter_state["block"],
            "filter_block_line": filter_state["block_line"],
            "filter_base_type_line": filter_state["base_type_line"],
        }

        if row["value_ex"] >= threshold_ex and filter_state["block"] == "Hide":
            hidden_but_should_show.append(report_row)
        elif row["value_ex"] < threshold_ex and filter_state["block"] == "Show":
            shown_but_should_hide.append(report_row)

    return {
        "threshold_ex": min_value_ex,
        "category_thresholds_ex": category_thresholds_ex,
        "shown_but_should_hide": shown_but_should_hide,
        "hidden_but_should_show": hidden_but_should_show,
        "unmatched_items": unmatched_items,
        "ignored_item_matches": ignored_item_matches,
        "summary": {
            "items_with_value": len(value_rows),
            "shown_but_should_hide": len(shown_but_should_hide),
            "hidden_but_should_show": len(hidden_but_should_show),
            "unmatched_items": len(unmatched_items),
            "ignored_item_matches": len(ignored_item_matches),
        },
    }


def chunked_names(names: list[str], chunk_size: int = 12) -> list[list[str]]:
    return [names[index : index + chunk_size] for index in range(0, len(names), chunk_size)]


def render_base_type_line(names: list[str]) -> str:
    quoted_names = " ".join(f'"{name}"' for name in names)
    return f"    BaseType == {quoted_names}"


def render_promote_block(names: list[str]) -> str:
    lines = [
        "Show",
        render_base_type_line(names),
        "    SetFontSize 45",
        "    SetTextColor 0 0 0 255",
        "    SetBorderColor 255 0 255 255",
        "    SetBackgroundColor 0 255 255 255",
        "    PlayAlertSound 2 175",
        "    PlayEffect Purple",
        "    MinimapIcon 0 Pink Star",
    ]
    return "\n".join(lines)


def render_hide_block(names: list[str]) -> str:
    lines = [
        "Hide",
        render_base_type_line(names),
    ]
    return "\n".join(lines)


def render_override_section(report: dict) -> str:
    hidden_but_should_show = sorted(
        {row["name"] for row in report["hidden_but_should_show"]}
    )
    shown_but_should_hide = sorted(
        {row["name"] for row in report["shown_but_should_hide"]}
    )

    blocks = [
        "#===============================================================================================================",
        "# AUTO-GENERATED OVERRIDES - poe-filter-updater",
        "# Promote hidden high-value items with loud debug styling for in-game validation.",
        "# Hide currently shown items that fall below the configured threshold.",
        "#===============================================================================================================",
    ]

    if hidden_but_should_show:
        blocks.append("# Promoted items: hidden by base filter, shown by updater")
        for names in chunked_names(hidden_but_should_show):
            blocks.append(render_promote_block(names))

    if shown_but_should_hide:
        blocks.append("# Demoted items: shown by base filter, hidden by updater")
        for names in chunked_names(shown_but_should_hide):
            blocks.append(render_hide_block(names))

    blocks.append("")
    return "\n\n".join(blocks)


def build_output_filter(input_filter_path: Path, report: dict) -> str:
    with input_filter_path.open("r", encoding="utf-8", errors="replace") as filter_file:
        original_filter = filter_file.read()

    original_filter = original_filter.replace(
        "#name:0.5 Twisters",
        "#name:PoE Filter Updater Debug",
        1,
    )

    override_section = render_override_section(report)
    return f"{override_section}\n{original_filter}"


def print_summary(
    snapshots: dict[str, dict], report: dict, output_dir: Path, report_path: Path, output_filter_path: Path
) -> None:
    for category, payload in snapshots.items():
        lines = payload.get("lines", [])
        category_path = output_path_for_category(output_dir, category)
        print(f"Saved {len(lines)} {category} entries to {category_path}")

    summary = report["summary"]
    print(
        "Generated threshold report with "
        f"{summary['shown_but_should_hide']} shown-but-should-hide, "
        f"{summary['hidden_but_should_show']} hidden-but-should-show, and "
        f"{summary['unmatched_items']} unmatched items at {report_path}"
    )
    print(f"Wrote updated filter to {output_filter_path}")


def main() -> int:
    args = parse_args()
    config = load_config(args.config)

    league = config["league"]
    min_value_ex = config["min_value_ex"]
    category_thresholds_ex = config.get("category_thresholds_ex", {})
    categories = config["categories"]
    ignored_items = set(config.get("ignored_items", []))
    output_dir = Path(config["poe_ninja_output_dir"])
    report_path = Path(config["report_output_path"])
    filter_path = Path(config["filter_path"])
    output_filter_path = Path(config["output_filter_path"])

    snapshots = fetch_category_snapshots(league, categories, output_dir)
    value_rows = build_value_rows(snapshots)
    filter_states = load_filter_first_match_states(filter_path)
    report = build_threshold_report(
        value_rows,
        filter_states,
        min_value_ex,
        category_thresholds_ex,
        ignored_items,
    )
    save_json(report_path, report)
    updated_filter = build_output_filter(filter_path, report)
    write_text(output_filter_path, updated_filter)
    print_summary(snapshots, report, output_dir, report_path, output_filter_path)
    return 0
