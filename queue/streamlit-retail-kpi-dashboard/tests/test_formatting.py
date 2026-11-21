from retail_kpi.formatting import fmt_delta, fmt_eur


def test_fmt_eur_scales():
    assert fmt_eur(2_768_316.15) == "€2.77M"
    assert fmt_eur(48_312) == "€48.3k"
    assert fmt_eur(9_950.4) == "€9,950"
    assert fmt_eur(88) == "€88"


def test_fmt_delta():
    assert fmt_delta(9.0) == "+9.0 %"
    assert fmt_delta(-0.42, "pp") == "-0.4 pp"
    assert fmt_delta(None) is None
