"""Deterministic synthetic generator for NYC-TLC-style yellow taxi trips.

The output is SYNTHETIC: realistic shapes (rush hours, airport trips, card vs cash tips)
plus a known share of injected data-quality problems, so the cleaning logic has
something real to catch. It is not a sample of the official TLC data.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

HEADER = [
    "VendorID",
    "tpep_pickup_datetime",
    "tpep_dropoff_datetime",
    "passenger_count",
    "trip_distance",
    "PULocationID",
    "DOLocationID",
    "payment_type",
    "fare_amount",
    "tip_amount",
    "tolls_amount",
    "total_amount",
]
TS_FMT = "%Y-%m-%d %H:%M:%S"
DEFAULT_ZONES = Path(__file__).resolve().parents[2] / "data" / "reference" / "taxi_zones.csv"

# Relative pickup volume per hour of day (index = hour).
HOUR_WEIGHTS = [
    3, 2, 1.5, 1, 1, 1.5, 3, 5, 6.5, 6, 5, 5, 5.5, 5.5, 6, 6.5, 6.5, 7, 7.5, 7, 6, 5.5, 5, 4
]
# Probability of each injected defect per generated row.
DEFECT_RATES = {
    "duplicate": 0.010,
    "zero_distance": 0.006,
    "null_passenger": 0.005,
    "negative_fare": 0.003,
    "dropoff_before_pickup": 0.003,
    "unknown_zone": 0.002,
    "too_long": 0.001,
}


@dataclass(frozen=True)
class Zone:
    location_id: int
    borough: str
    name: str

    @property
    def is_airport(self) -> bool:
        return "Airport" in self.name


def load_zones(path: Path = DEFAULT_ZONES) -> list[Zone]:
    with path.open(newline="") as fh:
        return [
            Zone(int(r["LocationID"]), r["Borough"], r["Zone"]) for r in csv.DictReader(fh)
        ]


def _zone_weight(z: Zone) -> float:
    if z.is_airport:
        return 6.0
    if z.borough == "Manhattan":
        return 10.0
    if z.borough in {"Brooklyn", "Queens"}:
        return 2.5
    return 1.0


def _speed_mph(hour: int, rng: random.Random) -> float:
    base = 9.0 if hour in {8, 9, 17, 18} else 18.0 if hour < 6 else 12.0
    return max(3.0, rng.gauss(base, 2.5))


def _distance(pu: Zone, do: Zone, rng: random.Random) -> float:
    if pu.is_airport or do.is_airport:
        return max(0.3, rng.gauss(17.0, 4.0))
    if pu.borough == do.borough:
        return min(25.0, rng.lognormvariate(math.log(1.8), 0.55))
    return max(0.3, rng.gauss(7.5, 2.5))


def generate_trips(
    n_rows: int, start: datetime, days: int, zones: list[Zone], seed: int = 42
) -> list[list[object]]:
    """Generate ``n_rows`` raw trip rows (strings/numbers in CSV column order)."""
    rng = random.Random(seed)
    zone_weights = [_zone_weight(z) for z in zones]
    rows: list[list[object]] = []
    while len(rows) < n_rows:
        day = rng.randrange(days)
        pickup_day = start + timedelta(days=day)
        weekend = pickup_day.weekday() >= 5
        hour_w = [w * (1.4 if weekend and (h < 3 or h > 21) else 1.0) for h, w in
                  enumerate(HOUR_WEIGHTS)]
        hour = rng.choices(range(24), weights=hour_w)[0]
        pickup = pickup_day + timedelta(hours=hour, seconds=rng.randrange(3600))
        pu, do = rng.choices(zones, weights=zone_weights, k=2)
        if pu.is_airport and do.is_airport:
            do = rng.choice([z for z in zones if z.borough == "Manhattan"])

        distance = round(_distance(pu, do, rng), 2)
        speed = _speed_mph(hour, rng) * (1.8 if distance > 8 else 1.0)  # highways
        minutes = distance / speed * 60 + rng.uniform(1, 4)
        dropoff = pickup + timedelta(seconds=int(minutes * 60))
        fare = round(3.0 + 2.5 * distance + 0.5 * minutes, 2)
        if pu.location_id == 132 or do.location_id == 132:
            fare = max(fare, 70.0)  # flat-fare style JFK trips
        payment = 1 if rng.random() < 0.72 else 2
        tip = round(fare * max(0.0, rng.gauss(0.2, 0.06)), 2) if payment == 1 else 0.0
        tolls = 6.94 if (pu.is_airport or do.is_airport) and rng.random() < 0.6 else 0.0
        passengers: int | None = rng.choices([1, 2, 3, 4, 5, 6], [70, 15, 5, 3, 4, 3])[0]
        pu_id, do_id = pu.location_id, do.location_id

        # Inject data-quality defects at known rates.
        r = rng.random()
        cut = 0.0
        defect = None
        for name, rate in DEFECT_RATES.items():
            cut += rate
            if r < cut:
                defect = name
                break
        if defect == "zero_distance":
            distance = 0.0
        elif defect == "null_passenger":
            passengers = None
        elif defect == "negative_fare":
            fare = -fare
        elif defect == "dropoff_before_pickup":
            dropoff = pickup - timedelta(minutes=rng.randint(1, 30))
        elif defect == "unknown_zone":
            pu_id = 999
        elif defect == "too_long":
            dropoff = pickup + timedelta(hours=rng.randint(7, 20))

        total = round(fare + tip + tolls + 2.5, 2)  # 2.5 = flat surcharges
        row: list[object] = [
            rng.choice([1, 2]),
            pickup.strftime(TS_FMT),
            dropoff.strftime(TS_FMT),
            "" if passengers is None else passengers,
            distance,
            pu_id,
            do_id,
            payment,
            fare,
            tip,
            tolls,
            total,
        ]
        rows.append(row)
        if defect == "duplicate" and len(rows) < n_rows:
            rows.append(list(row))  # re-delivered record
    return rows


def write_monthly_csv(rows: list[list[object]], out_dir: Path) -> list[Path]:
    """Write one CSV per pickup month, mimicking how TLC publishes monthly files."""
    out_dir.mkdir(parents=True, exist_ok=True)
    by_month: dict[str, list[list[object]]] = {}
    for row in rows:
        by_month.setdefault(str(row[1])[:7], []).append(row)
    paths = []
    for month, month_rows in sorted(by_month.items()):
        path = out_dir / f"yellow_tripdata_{month}.csv"
        with path.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(HEADER)
            writer.writerows(month_rows)
        paths.append(path)
    return paths


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows", type=int, default=150_000)
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--zones", type=Path, default=DEFAULT_ZONES)
    parser.add_argument("--out", type=Path, default=Path("data/raw/trips"))
    args = parser.parse_args(argv)

    rows = generate_trips(
        args.rows, datetime.fromisoformat(args.start), args.days, load_zones(args.zones),
        args.seed,
    )
    paths = write_monthly_csv(rows, args.out)
    print(f"Wrote {len(rows):,} synthetic trips to {len(paths)} files in {args.out}")


if __name__ == "__main__":
    main()
