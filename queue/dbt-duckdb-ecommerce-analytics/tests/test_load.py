from pathlib import Path

import duckdb
import pytest

from ecom.load import RAW_TABLES, load_raw


def test_load_creates_all_raw_tables(raw_dir: Path, tmp_path: Path) -> None:
    db = tmp_path / "wh.duckdb"
    counts = load_raw(raw_dir, db)
    assert set(counts) == set(RAW_TABLES)
    with duckdb.connect(str(db)) as con:
        types = {r[0] for r in con.execute(
            "select data_type from information_schema.columns "
            "where table_schema = 'raw' and column_name <> '_ingested_at'").fetchall()}
    assert types == {"VARCHAR"}, "raw layer must not apply typing"


def test_load_is_idempotent(raw_dir: Path, tmp_path: Path) -> None:
    db = tmp_path / "wh.duckdb"
    first = load_raw(raw_dir, db)
    second = load_raw(raw_dir, db)
    assert first == second


def test_missing_extract_raises(tmp_path: Path) -> None:
    (tmp_path / "customers.csv").write_text("customer_id\n1\n")
    with pytest.raises(FileNotFoundError, match="orders"):
        load_raw(tmp_path, tmp_path / "wh.duckdb")
