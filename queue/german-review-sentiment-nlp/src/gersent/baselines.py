"""Classical TF-IDF baselines built with scikit-learn pipelines."""

from __future__ import annotations

from collections.abc import Callable

from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

from gersent.text import normalize, tokenize, tokenize_with_negation


def majority() -> Pipeline:
    """Always predicts the most frequent class - the floor every model must beat."""
    return Pipeline([("tfidf", TfidfVectorizer(max_features=10)),
                     ("clf", DummyClassifier(strategy="most_frequent"))])


def tfidf_word_lr() -> Pipeline:
    """Word uni+bigrams, logistic regression with balanced class weights."""
    return Pipeline([
        ("tfidf", TfidfVectorizer(tokenizer=tokenize, token_pattern=None, lowercase=False,
                                  ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
        ("clf", LogisticRegression(C=4.0, max_iter=2000, class_weight="balanced")),
    ])


def tfidf_word_negation_lr() -> Pipeline:
    """Same as :func:`tfidf_word_lr` but tokens in a negation scope get a ``NEG_`` prefix."""
    return Pipeline([
        ("tfidf", TfidfVectorizer(tokenizer=tokenize_with_negation, token_pattern=None,
                                  lowercase=False, ngram_range=(1, 2), min_df=2,
                                  sublinear_tf=True)),
        ("clf", LogisticRegression(C=4.0, max_iter=2000, class_weight="balanced")),
    ])


def tfidf_char_svm() -> Pipeline:
    """Character 2-5 grams (robust to typos and compounds), linear SVM."""
    return Pipeline([
        ("tfidf", TfidfVectorizer(preprocessor=normalize, analyzer="char_wb",
                                  ngram_range=(2, 5), min_df=2, sublinear_tf=True)),
        ("clf", LinearSVC(C=0.5, class_weight="balanced")),
    ])


BASELINES: dict[str, Callable[[], Pipeline]] = {
    "majority_class": majority,
    "tfidf_word_lr": tfidf_word_lr,
    "tfidf_word_negation_lr": tfidf_word_negation_lr,
    "tfidf_char_svm": tfidf_char_svm,
}
