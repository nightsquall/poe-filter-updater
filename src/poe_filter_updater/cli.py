from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from poe_filter_updater.fetch import CATEGORY_SPECS, fetch_overview, output_path_for_category

RARITY_ORDER = {"Normal": 0, "Magic": 1, "Rare": 2, "Unique": 3}
UNIQUE_STASH_CATEGORIES = {
    "UniqueWeapons",
    "UniqueArmours",
    "UniqueAccessories",
    "UniqueFlasks",
    "UniqueCharms",
    "UniqueJewels",
    "UniqueSanctumRelics",
}
PRECURSOR_TABLET_CATEGORIES = {"PrecursorTablets"}
VARIANT_TO_RARITY = {
    "Normal": "Normal",
    "Magic": "Magic",
    "Rare": "Rare",
}


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
    for name, block in load_filter_first_match_blocks(filter_path).items():
        states[name] = {
            "block": block["block"],
            "block_line": block["block_line"],
            "base_type_line": block["base_type_line"],
        }
    return states


def parse_rarity_condition(line: str) -> tuple[str, str] | None:
    match = re.match(r"Rarity\s*(==|=|!=|>=|<=|>|<)?\s*(Normal|Magic|Rare|Unique)", line)
    if match is None:
        return None
    operator = match.group(1) or "="
    rarity = match.group(2)
    return operator, rarity


def load_filter_blocks(filter_path: Path) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    current_block: dict[str, object] | None = None

    with filter_path.open("r", encoding="utf-8", errors="replace") as filter_file:
        for line_number, raw_line in enumerate(filter_file, start=1):
            line = raw_line.strip()
            if line.startswith(("Show", "Hide", "Minimal")):
                if current_block is not None:
                    blocks.append(current_block)
                current_block = {
                    "block": line.split()[0],
                    "block_line": line_number,
                    "base_type_line": None,
                    "names": [],
                    "actions": [],
                    "rarity_condition": None,
                }
                continue

            if current_block is None:
                continue

            if line.startswith((
                "SetFontSize",
                "SetTextColor",
                "SetBorderColor",
                "SetBackgroundColor",
                "PlayAlertSound",
                "PlayAlertSoundPositional",
                "CustomAlertSound",
                "CustomAlertSoundOptional",
                "PlayEffect",
                "MinimapIcon",
            )):
                current_block["actions"].append(line)

            if line.startswith("Rarity") and current_block["rarity_condition"] is None:
                current_block["rarity_condition"] = parse_rarity_condition(line)

            if "BaseType" not in line:
                continue

            if current_block["base_type_line"] is None:
                current_block["base_type_line"] = line_number

            current_block["names"].extend(re.findall(r'"([^"]+)"', line))

    if current_block is not None:
        blocks.append(current_block)

    return blocks


def load_filter_first_match_blocks(filter_path: Path) -> dict[str, dict[str, object]]:
    states: dict[str, dict[str, object]] = {}
    for block in load_filter_blocks(filter_path):
        block_state = {
            "block": block["block"],
            "block_line": block["block_line"],
            "base_type_line": block["base_type_line"],
            "actions": tuple(block["actions"]),
        }
        for name in block["names"]:
            states.setdefault(name, block_state)

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
    rows_by_key: dict[tuple[str, str, str], dict] = {}
    primary_currency_values = exalt_value_by_primary_currency(snapshots["Currency"])

    for category, payload in snapshots.items():
        primary_currency = payload["core"]["primary"]
        ex_per_primary = primary_currency_values.get(primary_currency)
        if ex_per_primary is None:
            raise KeyError(f"No exalt conversion available for primary currency '{primary_currency}'")

        item_names = {item["id"]: item.get("name") or item.get("baseType") for item in payload.get("items", [])}

        for line in payload.get("lines", []):
            item_id = line["id"]
            name = item_names.get(item_id) or line.get("name") or line.get("baseType")
            if name is None:
                continue

            base_type = line.get("baseType", name)
            primary_value = line["primaryValue"]
            value_ex = primary_value * ex_per_primary

            if category in PRECURSOR_TABLET_CATEGORIES:
                match_mode = "base_type_rarity"
                match_key = base_type
                rarity = VARIANT_TO_RARITY.get(line.get("variant"))
            elif category in UNIQUE_STASH_CATEGORIES:
                match_mode = "unique_base_type"
                match_key = base_type
                rarity = "Unique"
            else:
                match_mode = "name"
                match_key = name
                rarity = line.get("rarity")

            row_key = (category, match_mode, match_key)
            row = {
                "category": category,
                "id": item_id,
                "name": name,
                "base_type": base_type,
                "match_key": match_key,
                "match_mode": match_mode,
                "rarity": rarity,
                "primary_value": primary_value,
                "primary_currency": primary_currency,
                "max_volume_currency": line.get("maxVolumeCurrency"),
                "max_volume_rate": line.get("maxVolumeRate"),
                "value_ex": value_ex,
            }
            existing = rows_by_key.get(row_key)
            if existing is None or row["value_ex"] > existing["value_ex"]:
                rows_by_key[row_key] = row

    rows = list(rows_by_key.values())
    rows.sort(key=lambda row: row["value_ex"], reverse=True)
    return rows


def rarity_matches_condition(item_rarity: str | None, condition: tuple[str, str] | None) -> bool:
    if condition is None:
        return True
    if item_rarity is None:
        return False

    operator, condition_rarity = condition
    left = RARITY_ORDER[item_rarity]
    right = RARITY_ORDER[condition_rarity]

    if operator in {"=", "=="}:
        return left == right
    if operator == "!=" or operator == "!":
        return left != right
    if operator == ">":
        return left > right
    if operator == ">=":
        return left >= right
    if operator == "<":
        return left < right
    if operator == "<=":
        return left <= right
    return False


def find_first_matching_filter_block(row: dict, filter_blocks: list[dict[str, object]]) -> dict[str, object] | None:
    if row["match_mode"] == "unique_base_type":
        target_name = row["base_type"]
    else:
        target_name = row["match_key"]

    for block in filter_blocks:
        if target_name not in block["names"]:
            continue
        if not rarity_matches_condition(row.get("rarity"), block.get("rarity_condition")):
            continue
        return {
            "block": block["block"],
            "block_line": block["block_line"],
            "base_type_line": block["base_type_line"],
            "actions": tuple(block["actions"]),
        }

    return None


def build_threshold_report(
    value_rows: list[dict],
    filter_blocks: list[dict[str, object]],
    min_value_ex: float,
    category_thresholds_ex: dict[str, float],
    ignored_items: set[str],
    always_show_unique_rings: bool,
    unique_ring_base_types: set[str],
) -> dict:
    shown_but_should_hide: list[dict] = []
    hidden_but_should_show: list[dict] = []
    unmatched_items: list[dict] = []
    ignored_item_matches: list[dict] = []
    always_shown_unique_rings: list[dict] = []

    for row in value_rows:
        threshold_ex = category_thresholds_ex.get(row["category"], min_value_ex)

        if row["name"] in ignored_items:
            ignored_item_matches.append({**row, "threshold_ex": threshold_ex})
            continue

        if (
            always_show_unique_rings
            and row["category"] == "UniqueAccessories"
            and row["base_type"] in unique_ring_base_types
        ):
            always_shown_unique_rings.append({**row, "threshold_ex": threshold_ex})
            continue

        filter_state = find_first_matching_filter_block(row, filter_blocks)
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
        "always_shown_unique_rings": always_shown_unique_rings,
        "summary": {
            "items_with_value": len(value_rows),
            "shown_but_should_hide": len(shown_but_should_hide),
            "hidden_but_should_show": len(hidden_but_should_show),
            "unmatched_items": len(unmatched_items),
            "ignored_item_matches": len(ignored_item_matches),
            "always_shown_unique_rings": len(always_shown_unique_rings),
        },
    }


def has_divine_like_effect(actions: tuple[str, ...]) -> bool:
    has_white_background = any(action == "SetBackgroundColor 255 255 255 255" for action in actions)
    has_alert_sound = any(
        action.startswith(("PlayAlertSound", "PlayAlertSoundPositional", "CustomAlertSound", "CustomAlertSoundOptional"))
        for action in actions
    )
    return has_white_background and has_alert_sound


def build_divine_style_report(
    value_rows: list[dict],
    filter_blocks: list[dict[str, object]],
    ignored_items: set[str],
    enabled: bool,
) -> dict:
    if not enabled:
        return {
            "enabled": False,
            "threshold_ex": 50.0,
            "divine_style_candidates": [],
            "divine_style_unmatched": [],
            "summary": {"divine_style_candidates": 0, "divine_style_unmatched": 0},
        }

    candidates: list[dict] = []
    unmatched: list[dict] = []
    for row in value_rows:
        if row["value_ex"] <= 50 or row["name"] in ignored_items:
            continue

        filter_block = find_first_matching_filter_block(row, filter_blocks)
        if filter_block is None:
            unmatched.append(row)
            continue

        actions = tuple(filter_block["actions"])
        if has_divine_like_effect(actions):
            continue

        candidates.append(
            {
                **row,
                "filter_block": filter_block["block"],
                "filter_block_line": filter_block["block_line"],
                "filter_base_type_line": filter_block["base_type_line"],
                "filter_actions": list(actions),
            }
        )

    return {
        "enabled": True,
        "threshold_ex": 50.0,
        "divine_style_candidates": candidates,
        "divine_style_unmatched": unmatched,
        "summary": {
            "divine_style_candidates": len(candidates),
            "divine_style_unmatched": len(unmatched),
        },
    }


def chunked_names(names: list[str], chunk_size: int = 12) -> list[list[str]]:
    return [names[index : index + chunk_size] for index in range(0, len(names), chunk_size)]


def render_base_type_line(names: list[str]) -> str:
    quoted_names = " ".join(f'"{name}"' for name in names)
    return f"    BaseType == {quoted_names}"


def render_show_block(names: list[str], actions: list[str], rarity: str | None = None) -> str:
    lines = ["Show"]
    if rarity is not None:
        lines.append(f"    Rarity {rarity}")
    lines.append(render_base_type_line(names))
    lines.extend(actions)
    return "\n".join(lines)


def render_promote_block(names: list[str]) -> str:
    return render_show_block(
        names,
        [
        "    SetFontSize 45",
        "    SetTextColor 0 0 0 255",
        "    SetBorderColor 255 0 255 255",
        "    SetBackgroundColor 0 255 255 255",
        "    PlayAlertSound 2 175",
        "    PlayEffect Purple",
        "    MinimapIcon 0 Pink Star",
        ],
    )


def render_divine_style_block(names: list[str]) -> str:
    return render_show_block(
        names,
        [
        "    SetFontSize 45",
        "    SetTextColor 255 0 0 255",
        "    SetBorderColor 255 0 0 255",
        "    SetBackgroundColor 235 255 255 255",
            "    PlayAlertSound 6 300",
            "    PlayEffect Red",
            "    MinimapIcon 0 Red Star",
        ],
    )


def render_unique_divine_style_block(names: list[str]) -> str:
    return render_show_block(
        names,
        [
            "    SetFontSize 45",
            "    SetTextColor 255 0 0 255",
            "    SetBorderColor 255 0 0 255",
            "    SetBackgroundColor 180 255 255 255",
            "    PlayAlertSound 6 300",
            "    PlayEffect Red",
            "    MinimapIcon 0 Red Star",
        ],
        rarity="Unique",
    )


def render_unique_promote_block(names: list[str]) -> str:
    return render_show_block(
        names,
        [
            "    SetFontSize 45",
            "    SetTextColor 0 0 0 255",
            "    SetBorderColor 255 0 255 255",
            "    SetBackgroundColor 0 200 255 255",
            "    PlayAlertSound 2 175",
            "    PlayEffect Purple",
            "    MinimapIcon 0 Pink Star",
        ],
        rarity="Unique",
    )


def render_unique_ring_override_block(names: list[str]) -> str:
    return render_show_block(
        names,
        [
            "    SetFontSize 42",
            "    SetTextColor 0 0 0 255",
            "    SetBorderColor 0 0 0 255",
            "    SetBackgroundColor 255 210 120 255",
            "    PlayAlertSound 3 300",
            "    PlayEffect Blue",
            "    MinimapIcon 1 Blue Star",
        ],
        rarity="Unique",
    )


def render_hide_block(names: list[str], rarity: str | None = None) -> str:
    lines = [
        "Hide",
    ]
    if rarity is not None:
        lines.append(f"    Rarity {rarity}")
    lines.append(render_base_type_line(names))
    return "\n".join(lines)


def group_rows_by_rarity(rows: list[dict], match_mode: str) -> dict[str, list[str]]:
    groups: dict[str, set[str]] = {}
    for row in rows:
        if row["match_mode"] != match_mode or row.get("rarity") is None:
            continue
        groups.setdefault(row["rarity"], set()).add(row_identifier(row))
    return {rarity: sorted(names) for rarity, names in groups.items()}


def row_identifier(row: dict) -> str:
    return row["match_key"] if row["match_mode"] == "unique_base_type" else row["name"]


def render_override_section(report: dict) -> str:
    divine_style_rows = report.get("divine_style_candidates", [])
    threshold_show_rows = report["hidden_but_should_show"]
    threshold_hide_rows = report["shown_but_should_hide"]
    unique_ring_rows = report.get("always_shown_unique_rings", [])

    divine_style_candidates = sorted({row_identifier(row) for row in divine_style_rows if row["match_mode"] == "name"})
    unique_divine_style_candidates = sorted({row_identifier(row) for row in divine_style_rows if row["match_mode"] == "unique_base_type"})
    precursor_divine_style_candidates = group_rows_by_rarity(divine_style_rows, "base_type_rarity")
    hidden_but_should_show = sorted({row_identifier(row) for row in threshold_show_rows if row["match_mode"] == "name"})
    unique_hidden_but_should_show = sorted({row_identifier(row) for row in threshold_show_rows if row["match_mode"] == "unique_base_type"})
    precursor_hidden_but_should_show = group_rows_by_rarity(threshold_show_rows, "base_type_rarity")
    shown_but_should_hide = sorted({row_identifier(row) for row in threshold_hide_rows if row["match_mode"] == "name"})
    unique_shown_but_should_hide = sorted({row_identifier(row) for row in threshold_hide_rows if row["match_mode"] == "unique_base_type"})
    precursor_shown_but_should_hide = group_rows_by_rarity(threshold_hide_rows, "base_type_rarity")
    always_show_unique_rings = sorted({row_identifier(row) for row in unique_ring_rows})

    blocks = [
        "#===============================================================================================================",
        "# AUTO-GENERATED OVERRIDES - poe-filter-updater",
        "# Promote hidden high-value items with loud debug styling for in-game validation.",
        "# Hide currently shown items that fall below the configured threshold.",
        "#===============================================================================================================",
    ]

    if divine_style_candidates:
        blocks.append("# Divine-style overrides for items worth over 50 exalted orbs")
        for names in chunked_names(divine_style_candidates):
            blocks.append(render_divine_style_block(names))

    if unique_divine_style_candidates:
        blocks.append("# Divine-style overrides for unique items worth over 50 exalted orbs")
        for names in chunked_names(unique_divine_style_candidates):
            blocks.append(render_unique_divine_style_block(names))

    if precursor_divine_style_candidates:
        blocks.append("# Divine-style overrides for precursor tablets worth over 50 exalted orbs")
        for rarity in ("Normal", "Magic", "Rare"):
            names = precursor_divine_style_candidates.get(rarity, [])
            for chunk in chunked_names(names):
                blocks.append(render_show_block(
                    chunk,
                    [
                        "    SetFontSize 45",
                        "    SetTextColor 255 0 0 255",
                        "    SetBorderColor 255 0 0 255",
                        "    SetBackgroundColor 235 255 255 255",
                        "    PlayAlertSound 6 300",
                        "    PlayEffect Red",
                        "    MinimapIcon 0 Red Star",
                    ],
                    rarity=rarity,
                ))

    if hidden_but_should_show:
        blocks.append("# Promoted items: hidden by base filter, shown by updater")
        for names in chunked_names(hidden_but_should_show):
            blocks.append(render_promote_block(names))

    if unique_hidden_but_should_show:
        blocks.append("# Promoted unique base types: hidden by base filter, shown by updater")
        for names in chunked_names(unique_hidden_but_should_show):
            blocks.append(render_unique_promote_block(names))

    if precursor_hidden_but_should_show:
        blocks.append("# Promoted precursor tablets: hidden by base filter, shown by updater")
        for rarity in ("Normal", "Magic", "Rare"):
            names = precursor_hidden_but_should_show.get(rarity, [])
            for chunk in chunked_names(names):
                blocks.append(render_show_block(
                    chunk,
                    [
                        "    SetFontSize 45",
                        "    SetTextColor 0 0 0 255",
                        "    SetBorderColor 255 0 255 255",
                        "    SetBackgroundColor 0 255 255 255",
                        "    PlayAlertSound 2 175",
                        "    PlayEffect Purple",
                        "    MinimapIcon 0 Pink Star",
                    ],
                    rarity=rarity,
                ))

    if always_show_unique_rings:
        blocks.append("# Always show unique rings for vendor recipe")
        for names in chunked_names(always_show_unique_rings):
            blocks.append(render_unique_ring_override_block(names))

    if shown_but_should_hide:
        blocks.append("# Demoted items: shown by base filter, hidden by updater")
        for names in chunked_names(shown_but_should_hide):
            blocks.append(render_hide_block(names))

    if unique_shown_but_should_hide:
        blocks.append("# Demoted unique base types: shown by base filter, hidden by updater")
        for names in chunked_names(unique_shown_but_should_hide):
            blocks.append(render_hide_block(names, rarity="Unique"))

    if precursor_shown_but_should_hide:
        blocks.append("# Demoted precursor tablets: shown by base filter, hidden by updater")
        for rarity in ("Normal", "Magic", "Rare"):
            names = precursor_shown_but_should_hide.get(rarity, [])
            for chunk in chunked_names(names):
                blocks.append(render_hide_block(chunk, rarity=rarity))

    blocks.append("")
    return "\n\n".join(blocks)


def build_output_filter(input_filter_path: Path, report: dict) -> str:
    with input_filter_path.open("r", encoding="utf-8", errors="replace") as filter_file:
        original_filter = filter_file.read()

    original_filter = original_filter.replace(
        "#name:0.5 Twisters",
        "#name:PoE Filter Updater Divine50 Debug",
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
    divine_summary = report["divine_style_summary"]
    print(
        "Generated threshold report with "
        f"{summary['shown_but_should_hide']} shown-but-should-hide, "
        f"{summary['hidden_but_should_show']} hidden-but-should-show, and "
        f"{summary['unmatched_items']} unmatched items at {report_path}"
    )
    print(f"Always-show unique ring overrides cover {summary['always_shown_unique_rings']} rows")
    print(
        "Divine-style feature found "
        f"{divine_summary['divine_style_candidates']} candidates and "
        f"{divine_summary['divine_style_unmatched']} unmatched high-value items"
    )
    print(f"Wrote updated filter to {output_filter_path}")


def main() -> int:
    args = parse_args()
    config = load_config(args.config)

    league = config["league"]
    min_value_ex = config["min_value_ex"]
    category_thresholds_ex = config.get("category_thresholds_ex", {})
    enable_divine_style_for_50ex = config.get("enable_divine_style_for_50ex", False)
    always_show_unique_rings = config.get("always_show_unique_rings", False)
    categories = config["categories"]
    ignored_items = set(config.get("ignored_items", []))
    output_dir = Path(config["poe_ninja_output_dir"])
    report_path = Path(config["report_output_path"])
    filter_path = Path(config["filter_path"])
    output_filter_path = Path(config["output_filter_path"])

    snapshots = fetch_category_snapshots(league, categories, output_dir)
    unique_ring_base_types = {
        line.get("baseType")
        for line in snapshots.get("UniqueAccessories", {}).get("lines", [])
        if line.get("category") == "Ring" and line.get("baseType")
    }
    value_rows = build_value_rows(snapshots)
    filter_blocks = load_filter_blocks(filter_path)
    report = build_threshold_report(
        value_rows,
        filter_blocks,
        min_value_ex,
        category_thresholds_ex,
        ignored_items,
        always_show_unique_rings,
        unique_ring_base_types,
    )
    divine_style_report = build_divine_style_report(
        value_rows,
        filter_blocks,
        ignored_items,
        enable_divine_style_for_50ex,
    )
    report["divine_style_candidates"] = divine_style_report["divine_style_candidates"]
    report["divine_style_unmatched"] = divine_style_report["divine_style_unmatched"]
    report["divine_style_summary"] = divine_style_report["summary"]
    report["enable_divine_style_for_50ex"] = enable_divine_style_for_50ex
    save_json(report_path, report)
    updated_filter = build_output_filter(filter_path, report)
    write_text(output_filter_path, updated_filter)
    print_summary(snapshots, report, output_dir, report_path, output_filter_path)
    return 0
