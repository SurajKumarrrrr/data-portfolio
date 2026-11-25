import pandas as pd
import pytest

from gersent.data import LABELS, generate_reviews, star_to_label, train_val_test_split


@pytest.mark.parametrize(("stars", "label"),
                         [(1, "negativ"), (2, "negativ"), (3, "neutral"), (4, "positiv"),
                          (5, "positiv")])
def test_star_to_label(stars, label):
    assert star_to_label(stars) == label


def test_generator_is_deterministic():
    a = generate_reviews(200, seed=7)
    b = generate_reviews(200, seed=7)
    pd.testing.assert_frame_equal(a, b)
    assert not a.equals(generate_reviews(200, seed=8))


def test_generator_schema_and_labels(reviews):
    assert list(reviews.columns) == ["review_id", "category", "stars", "text", "label"]
    assert set(reviews["label"]) == set(LABELS)
    assert reviews["text"].str.len().min() > 10
    assert (reviews["label"] == reviews["stars"].map(star_to_label)).all()


def test_no_label_noise_means_one_star_reviews_have_no_positive_closer():
    df = generate_reviews(800, seed=3, label_noise=0.0)
    one_star = df[df["stars"] == 1]["text"]
    assert not one_star.str.contains("Klare Kaufempfehlung").any()


def test_split_is_stratified_and_disjoint(reviews):
    train, val, test = train_val_test_split(reviews, seed=1)
    ids = [set(x["review_id"]) for x in (train, val, test)]
    assert not (ids[0] & ids[1]) and not (ids[0] & ids[2]) and not (ids[1] & ids[2])
    assert sum(map(len, ids)) == len(reviews)
    full = reviews["label"].value_counts(normalize=True)
    part = test["label"].value_counts(normalize=True)
    assert (full - part).abs().max() < 0.02
