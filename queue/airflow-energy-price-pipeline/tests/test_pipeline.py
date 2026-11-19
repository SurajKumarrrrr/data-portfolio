from datetime import date

import duckdb
import pytest

from energy_pipeline.__main__ import main
from energy_pipeline.pipeline import Settings, backfill, run_day, step_validate
from energy_pipeline.report import build_report
from energy_pipeline.sources import SyntheticSmardSource
from energy_pipeline.transform import DataQualityError


@pytest.fixture
def settings(tmp_path):
    return Settings(raw_dir=tmp_path / "raw", db_path=tmp_path / "wh.duckdb", source="synthetic")


def test_backfill_over_dst_and_rerun(settings):
    start, end = date(2025, 3, 28), date(2025, 4, 2)
    first = backfill(start, end, settings)
    assert all(r.status == "loaded" for r in first)
    assert sum(r.rows_inserted for r in first) == 6 * 24 - 1  # 30 March has 23 hours
    second = backfill(start, end, settings)
    assert [r.rows_deleted for r in second] == [r.rows_inserted for r in first]
    con = duckdb.connect(str(settings.db_path), read_only=True)
    assert con.execute("SELECT count(*) FROM hourly_prices").fetchone()[0] == 143
    con.close()
    assert len(list((settings.raw_dir / "synthetic").glob("*.json"))) == 6


def test_quality_failure_skips_load(settings):
    bad = date(2025, 1, 10)
    result = run_day(bad, settings, SyntheticSmardSource(drop_hour_on={bad}))
    assert result.status == "failed_quality"
    assert "expected 24 hours" in result.error
    assert not settings.db_path.exists()  # nothing was written to the warehouse


def test_step_validate_raises(settings):
    from energy_pipeline.extract import extract_day

    bad = date(2025, 1, 10)
    path = extract_day(SyntheticSmardSource(drop_hour_on={bad}), bad, settings.raw_dir)
    with pytest.raises(DataQualityError):
        step_validate(str(path))


def test_report_and_cli(settings, monkeypatch, tmp_path):
    monkeypatch.setenv("ENERGY_RAW_DIR", str(settings.raw_dir))
    monkeypatch.setenv("ENERGY_DB_PATH", str(settings.db_path))
    assert main(["backfill", "--start", "2025-01-01", "--end", "2025-01-14"]) == 0
    assert main(["run", "--date", "2025-01-15"]) == 0
    out = tmp_path / "report.md"
    assert main(["report", "--out", str(out)]) == 0
    text = out.read_text()
    assert "| 2025-01 | 15 |" in text
    assert "**duplicate_rows**: 0" in text
    assert build_report(settings.db_path) == text


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("ENERGY_DATA_DIR", "/tmp/x")
    monkeypatch.delenv("ENERGY_RAW_DIR", raising=False)
    monkeypatch.delenv("ENERGY_DB_PATH", raising=False)
    monkeypatch.setenv("ENERGY_SOURCE", "smard")
    s = Settings.from_env()
    assert str(s.raw_dir) == "/tmp/x/raw" and str(s.db_path) == "/tmp/x/warehouse.duckdb"
    assert s.source == "smard"


def test_cli_reports_quality_failures(settings, monkeypatch, capsys):
    monkeypatch.setenv("ENERGY_RAW_DIR", str(settings.raw_dir))
    monkeypatch.setenv("ENERGY_DB_PATH", str(settings.db_path))
    code = main(["backfill", "--start", "2025-02-01", "--end", "2025-02-03", "--drop-hour-on", "2025-02-02"])
    assert code == 1
    out = capsys.readouterr().out
    assert "'loaded': 2" in out and "'failed_quality': 1" in out and "2025-02-02" in out
