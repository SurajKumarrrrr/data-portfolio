"""Download one month of the official NYC TLC yellow-taxi data plus the zone lookup.

Not needed for tests or the default demo (which use synthetic data). Run it to process
real data:

    python scripts/download_data.py --month 2024-01
    PYTHONPATH=src python -m taxi_batch.job --format parquet \
        --input data/tlc/yellow_tripdata_2024-01.parquet \
        --zones data/tlc/taxi_zone_lookup.csv --output data/output_tlc

Source: https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page
"""

from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path

BASE = "https://d37ci6vzurychx.cloudfront.net"


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"exists, skipping: {dest}")
        return
    print(f"downloading {url}")
    urllib.request.urlretrieve(url, dest)  # noqa: S310 - fixed https host


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--month", default="2024-01", help="YYYY-MM")
    parser.add_argument("--out", type=Path, default=Path("data/tlc"))
    args = parser.parse_args()
    name = f"yellow_tripdata_{args.month}.parquet"
    download(f"{BASE}/trip-data/{name}", args.out / name)
    download(f"{BASE}/misc/taxi_zone_lookup.csv", args.out / "taxi_zone_lookup.csv")


if __name__ == "__main__":
    main()
