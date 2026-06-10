# poe-filter-updater

Python utility for updating a local Path of Exile 2 item filter based on poe.ninja economy data.

## Planned Scope

- Fetch economy data from poe.ninja
- Apply a configurable minimum value threshold
- Update a generated section inside a local item filter
- Support non-gear economy items such as currency, fragments, omens, and gems

## Current Scope

- Fetch the current poe.ninja overview JSON for configured PoE 2 economy categories
- Save one response file per category for later filter processing
- Generate a threshold report that compares poe.ninja values against the current filter

## Proposed Layout

- `src/poe_filter_updater/` - package source
- `tests/` - test suite
- `config.example.json` - example user configuration

## Usage

Run the first iteration fetcher with:

```bash
PYTHONPATH=src python -m poe_filter_updater --config config.example.json
```

This will:

- fetch all configured poe.ninja category snapshots into `data/poe_ninja/`
- compute each item's value in exalted orbs
- generate a report of items that are currently shown but should hide, or hidden but should show
- write a new filter file with a generated override section at `output_filter_path`

## Config Notes

- `min_value_ex` is the global default threshold
- `category_thresholds_ex` optionally overrides `min_value_ex` per poe.ninja category
- `ignored_items` is an exact item-name list that the updater will not modify

Example:

```json
{
  "min_value_ex": 1.0,
  "category_thresholds_ex": {
    "Currency": 0.5,
    "Runes": 1.0
  },
  "ignored_items": [
    "Scroll of Wisdom"
  ]
}
```

## Status

Fetcher, threshold-reporting, and a first generated override filter are implemented.
