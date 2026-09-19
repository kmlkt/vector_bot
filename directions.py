"""Справочник направлений из data/directions.json (см. scoring.pick_directions)."""

import json
from pathlib import Path

DIRECTIONS_PATH = Path(__file__).resolve().parent / "data" / "directions.json"

with open(DIRECTIONS_PATH, encoding="utf-8") as f:
    DIRECTIONS: list[dict] = json.load(f)

DIRECTIONS_BY_ID = {d["id"]: d for d in DIRECTIONS}
