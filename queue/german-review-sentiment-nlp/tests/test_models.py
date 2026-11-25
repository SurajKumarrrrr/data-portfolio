import pytest

from gersent.baselines import BASELINES
from gersent.data import train_val_test_split
from gersent.evaluate import compute_metrics, error_examples, slice_metrics
from gersent.transformer import TransformerConfig, TransformerSentiment
from gersent.vocab import Vocab


@pytest.fixture(scope="module")
def split(reviews):
    return train_val_test_split(reviews, seed=5)


@pytest.mark.parametrize("name", ["tfidf_word_lr", "tfidf_word_negation_lr", "tfidf_char_svm"])
def test_baselines_clearly_beat_majority(split, name):
    train, _, test = split
    major = BASELINES["majority_class"]().fit(train["text"], train["label"])
    model = BASELINES[name]().fit(train["text"], train["label"])
    m_major = compute_metrics(test["label"], major.predict(test["text"]))
    m_model = compute_metrics(test["label"], model.predict(test["text"]))
    assert m_model["macro_f1"] > m_major["macro_f1"] + 0.4
    assert m_model["accuracy"] > 0.85


def test_negation_baseline_learns_negated_features(split):
    train, _, _ = split
    model = BASELINES["tfidf_word_negation_lr"]().fit(train["text"], train["label"])
    vocab = model.named_steps["tfidf"].vocabulary_
    assert "NEG_probleme" in vocab
    assert model.predict(["Der Akku ist nicht gut. Geht zurück."])[0] == "negativ"


def test_vocab_encode_pads_truncates_and_handles_unknown():
    v = Vocab.build(["gut gut schlecht", "gut"], min_freq=2)
    assert "gut" in v.stoi and "schlecht" not in v.stoi
    ids = v.encode("gut schlecht", max_len=5)
    assert ids == [2, v.stoi["gut"], 1, 0, 0]
    assert len(v.encode("gut " * 50, max_len=8)) == 8


def test_vocab_roundtrip(tmp_path):
    v = Vocab.build(["eins zwei zwei eins"], min_freq=1)
    v.save(tmp_path / "v.json")
    assert Vocab.load(tmp_path / "v.json").itos == v.itos


def test_tiny_transformer_trains_and_predicts(split):
    train, val, test = split
    cfg = TransformerConfig(d_model=32, n_heads=2, n_layers=1, ff_dim=64, max_epochs=4,
                            patience=4, max_len=64)
    model = TransformerSentiment(cfg).fit(train["text"].tolist(), train["label"].tolist(),
                                          val["text"].tolist(), val["label"].tolist())
    proba = model.predict_proba(test["text"].tolist()[:10])
    assert proba.shape == (10, 3)
    assert abs(proba.sum(axis=1) - 1).max() < 1e-5
    metrics = compute_metrics(test["label"].tolist(), model.predict(test["text"].tolist()))
    assert metrics["accuracy"] > 0.7
    assert model.history and model.n_parameters() > 0


def test_unfitted_transformer_raises():
    with pytest.raises(RuntimeError):
        TransformerSentiment().predict(["test"])


def test_metrics_slices_and_errors():
    y = ["positiv", "negativ", "neutral", "positiv"]
    p = ["positiv", "negativ", "positiv", "positiv"]
    m = compute_metrics(y, p)
    assert m["accuracy"] == 0.75
    assert m["confusion_matrix"][1][2] == 1  # neutral predicted as positiv
    texts = ["gut", "nicht gut", "okay, aber laut", "super"]
    s = slice_metrics(texts, y, p)
    assert s["with_negation"]["n"] == 1 and s["with_contrast"]["accuracy"] == 0.0
    assert error_examples(texts, y, p) == [{"text": "okay, aber laut", "true": "neutral",
                                             "pred": "positiv"}]
