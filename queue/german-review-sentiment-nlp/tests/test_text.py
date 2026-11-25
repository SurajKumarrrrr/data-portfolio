from gersent.text import (
    has_contrast,
    has_negation,
    is_transliterated,
    mark_negation,
    normalize,
    tokenize,
    tokenize_with_negation,
)


def test_normalize_folds_umlauts_and_case():
    assert normalize("Preis-Leistungs-Verhältnis GROß") == "preis-leistungs-verhaeltnis gross"
    assert normalize("Verhältnis") == normalize("Verhaeltnis")


def test_tokenize_keeps_hyphenated_compounds_and_punctuation():
    assert tokenize("Top Preis-Leistung, klasse!") == ["top", "preis-leistung", ",", "klasse", "!"]


def test_negation_scope_ends_at_punctuation():
    toks = mark_negation(["ist", "nicht", "gut", ".", "super"])
    assert toks == ["ist", "nicht", "NEG_gut", ".", "super"]


def test_negation_scope_ends_at_contrast_conjunction():
    toks = tokenize_with_negation("keine Probleme aber laut")
    assert toks == ["keine", "NEG_probleme", "aber", "laut"]


def test_slice_predicates():
    assert has_negation("Kann ich nicht empfehlen")
    assert not has_negation("Kann ich empfehlen")
    assert has_contrast("Schnell geliefert, aber kaputt")
    assert is_transliterated("Wuerde ich wieder kaufen")
    assert not is_transliterated("Würde ich wieder kaufen")
