import json

from gersent.cli import main
from gersent.pipeline import ExperimentConfig, run_experiment


def test_run_experiment_writes_reports(tmp_path):
    cfg = ExperimentConfig(n_reviews=900, seed=3)
    summary = run_experiment(cfg, out_dir=tmp_path,
                             models=["majority_class", "tfidf_word_negation_lr"])
    assert summary["data"]["synthetic"] is True
    assert [r["model"] for r in summary["results"]] == ["majority_class",
                                                         "tfidf_word_negation_lr"]
    saved = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert saved["results"][1]["challenge"]["n"] == 30
    assert "| tfidf_word_negation_lr |" in (tmp_path / "results.md").read_text()
    assert (tmp_path / "best_baseline.joblib").exists()


def test_cli_generate_and_predict(tmp_path, capsys):
    out = tmp_path / "reviews.csv"
    main(["generate", "--n", "50", "--out", str(out)])
    assert out.read_text(encoding="utf-8").count("\n") == 51
    run_experiment(ExperimentConfig(n_reviews=900, seed=3), out_dir=tmp_path,
                   models=["tfidf_word_lr"])
    capsys.readouterr()
    main(["predict", "Klare Kaufempfehlung, super Klang!", "--model",
          str(tmp_path / "best_baseline.joblib")])
    assert capsys.readouterr().out.startswith("positiv")
