import json

from dq_checks.cli import main


def test_cli_end_to_end(tmp_path, capsys):
    clean, dirty = tmp_path / "clean", tmp_path / "dirty"
    assert main(["generate", "--out", str(clean), "--customers", "60", "--clean"]) == 0
    assert main(["generate", "--out", str(dirty), "--customers", "80", "--defects-per-type", "1"]) == 0

    assert main(["validate", "--data-dir", str(clean), "--out-dir", str(tmp_path / "r1")]) == 0
    assert main(["validate", "--data-dir", str(dirty), "--out-dir", str(tmp_path / "r2")]) == 1
    assert main(["evaluate", "--data-dir", str(dirty), "--out-dir", str(tmp_path / "r3")]) == 0

    summary = json.loads((tmp_path / "r2" / "summary.json").read_text())
    assert summary["gate"]["passed"] is False
    assert summary["errors"] > 0
    report = (tmp_path / "r2" / "report.md").read_text()
    assert "Gate (error): FAILED" in report
    assert (tmp_path / "r2" / "quarantine" / "orders.csv").exists()
    assert "detected" in capsys.readouterr().out
