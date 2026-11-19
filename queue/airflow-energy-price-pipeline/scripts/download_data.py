"""Load REAL day-ahead prices from the public SMARD API (Bundesnetzagentur) into the warehouse.

Needs internet access. Example:
    PYTHONPATH=src python scripts/download_data.py --start 2025-01-01 --end 2025-03-31

SMARD data is published under CC BY 4.0 (source: Bundesnetzagentur | SMARD.de).
"""

from __future__ import annotations

import sys

from energy_pipeline.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main(["backfill", "--source", "smard", *sys.argv[1:]]))
