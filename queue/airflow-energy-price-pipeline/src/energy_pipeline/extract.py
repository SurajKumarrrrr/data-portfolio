"""Extract step: fetch one delivery day and land it unchanged as raw JSON (bronze layer)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from energy_pipeline.sources import PriceSource


def raw_path(raw_dir: Path, source_name: str, delivery_date: date) -> Path:
    return raw_dir / source_name / f"delivery_date={delivery_date.isoformat()}.json"


def extract_day(source: PriceSource, delivery_date: date, raw_dir: Path) -> Path:
    """Fetch the day and write it to the landing zone.

    The file name is derived only from source + date, so a re-run overwrites the
    previous file instead of creating duplicates. Writing goes through a temp file
    and an atomic rename so a crashed task never leaves a half-written file.
    """
    series = source.fetch_day(delivery_date)
    payload = {
        "source": source.name,
        "delivery_date": delivery_date.isoformat(),
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "series": series,
    }
    target = raw_path(raw_dir, source.name, delivery_date)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(target)
    return target


def read_raw(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
