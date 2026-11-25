"""Deterministic generator for synthetic German product reviews.

Real German review corpora (e.g. Amazon reviews) cannot be redistributed in this repo, so
we generate realistic-looking reviews from a star rating. The generator deliberately
includes the phenomena that make German sentiment hard for bag-of-words models:

* negation (``nicht gut``, ``keine Probleme``, ``kann ich nicht empfehlen``)
* contrast clauses where the clause after ``aber``/``doch`` carries the verdict
* neutral / mixed 3-star reviews
* spelling variants (``ae`` instead of ``ä``), typos and a small amount of label noise
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

LABELS: tuple[str, ...] = ("negativ", "neutral", "positiv")

CATEGORIES: dict[str, list[tuple[str, str]]] = {
    # category -> list of (aspect noun with article in nominative, short noun)
    "Kopfhörer": [("Der Klang", "Klang"), ("Der Akku", "Akku"),
                  ("Der Tragekomfort", "Tragekomfort"), ("Die Geräuschunterdrückung", "ANC")],
    "Kaffeemaschine": [("Der Kaffee", "Kaffee"), ("Die Reinigung", "Reinigung"),
                       ("Der Milchschäumer", "Milchschäumer"), ("Die Bedienung", "Bedienung")],
    "Staubsauger": [("Die Saugleistung", "Saugleistung"), ("Der Akku", "Akku"),
                    ("Die Lautstärke", "Lautstärke"), ("Der Behälter", "Behälter")],
    "Laufschuhe": [("Die Passform", "Passform"), ("Die Dämpfung", "Dämpfung"),
                   ("Die Sohle", "Sohle"), ("Das Material", "Material")],
    "Smartphone": [("Das Display", "Display"), ("Die Kamera", "Kamera"),
                   ("Der Akku", "Akku"), ("Die Software", "Software")],
    "Bohrmaschine": [("Die Leistung", "Leistung"), ("Der Koffer", "Koffer"),
                     ("Die Verarbeitung", "Verarbeitung"), ("Das Gewicht", "Gewicht")],
}

GENERIC_ASPECTS: list[tuple[str, str]] = [
    ("Die Lieferung", "Lieferung"), ("Die Verpackung", "Verpackung"),
    ("Der Kundenservice", "Kundenservice"), ("Das Preis-Leistungs-Verhältnis", "Preis"),
    ("Die Anleitung", "Anleitung"),
]

POS_ADJ = ["super", "hervorragend", "sehr gut", "einwandfrei", "klasse", "top",
           "überzeugend", "erstklassig", "wirklich gut", "prima"]
NEG_ADJ = ["schlecht", "enttäuschend", "mangelhaft", "katastrophal", "miserabel",
           "unbrauchbar", "sehr schwach", "ärgerlich", "billig", "furchtbar"]
NEU_ADJ = ["okay", "in Ordnung", "durchschnittlich", "solide", "akzeptabel", "mittelmäßig"]
# adjectives that flip cleanly under "nicht"
NEGATABLE_POS = ["gut", "überzeugend", "empfehlenswert", "zufriedenstellend", "brauchbar"]
NEGATABLE_NEG = ["schlecht", "enttäuschend", "mangelhaft", "verkehrt", "übel"]

POS_CLOSERS = ["Klare Kaufempfehlung!", "Ich kann das Produkt nur empfehlen.",
               "Würde ich jederzeit wieder kaufen.", "Volle Punktzahl von mir.",
               "Bin rundum zufrieden.", "Hat sich absolut gelohnt."]
NEG_CLOSERS = ["Würde ich nicht wieder kaufen.", "Ich kann das Produkt nicht empfehlen.",
               "Geht zurück.", "Finger weg!", "Leider ein Fehlkauf.",
               "Bin überhaupt nicht zufrieden."]
NEU_CLOSERS = ["Für den Preis okay.", "Erfüllt seinen Zweck.",
               "Kann man kaufen, muss man aber nicht.", "Nichts Besonderes.",
               "Mal sehen, wie lange es hält."]
CONTRASTS = ["aber", "aber", "doch"]

STAR_PROBS = np.array([0.17, 0.10, 0.13, 0.20, 0.40])  # 1..5 stars, J-shaped like real shops


def star_to_label(stars: int) -> str:
    """Map a 1-5 star rating to a 3-class sentiment label."""
    if stars <= 2:
        return "negativ"
    if stars == 3:
        return "neutral"
    return "positiv"


@dataclass
class _Gen:
    rng: np.random.Generator

    def pick(self, items):
        return items[int(self.rng.integers(len(items)))]

    def aspect(self, category: str) -> tuple[str, str]:
        pool = CATEGORIES[category] + GENERIC_ASPECTS
        return self.pick(pool)

    def clause(self, category: str, polarity: int) -> str:
        """One clause (no final punctuation) expressing ``polarity`` in {-1, 0, 1}."""
        subj, _ = self.aspect(category)
        if polarity == 0:
            return f"{subj} ist {self.pick(NEU_ADJ)}"
        style = self.rng.random()
        if style < 0.55:
            adj = self.pick(POS_ADJ if polarity > 0 else NEG_ADJ)
            return f"{subj} ist {adj}"
        if style < 0.85:  # negated opposite: "nicht schlecht" (pos) / "nicht gut" (neg)
            adj = self.pick(NEGATABLE_NEG if polarity > 0 else NEGATABLE_POS)
            return f"{subj} ist {'überhaupt ' if self.rng.random() < 0.2 else ''}nicht {adj}"
        art, noun = subj.split(" ", 1)
        dat = "dem" if art in ("Der", "Das") else "der"
        if polarity > 0:
            return self.pick([f"mit {dat} {noun} hatte ich keine Probleme",
                              f"an {dat} {noun} gibt es nichts auszusetzen",
                              f"von {dat} {noun} bin ich begeistert"])
        return self.pick([f"mit {dat} {noun} gab es ständig Probleme",
                          f"{subj} hat nach zwei Wochen den Geist aufgegeben",
                          f"von {dat} {noun} bin ich enttäuscht"])

    def sentence(self, category: str, polarity: int) -> str:
        c = self.clause(category, polarity)
        return c[0].upper() + c[1:] + "."

    def contrast(self, category: str, first: int, last: int) -> str:
        a = self.clause(category, first)
        b = self.clause(category, last)
        for _ in range(5):  # avoid "X is bad, but X is good" with the same aspect
            if a.split()[1] != b.split()[1]:
                break
            b = self.clause(category, last)
        text = f"{a}, {self.pick(CONTRASTS)} {b[0].lower() + b[1:]}"
        return text[0].upper() + text[1:] + "."

    def review(self, category: str, stars: int) -> str:
        n = int(self.rng.integers(2, 5))
        parts: list[str] = []
        if stars in (1, 5):
            pol = 1 if stars == 5 else -1
            parts = [self.sentence(category, pol) for _ in range(n)]
            if self.rng.random() < 0.3:
                parts.insert(0, f"{self.pick(['Gekauft', 'Bestellt'])} vor drei Wochen.")
            if self.rng.random() < 0.35:  # strong reviews often concede one point
                parts.append(self.contrast(category, -pol, pol))
        elif stars in (2, 4):
            pol = 1 if stars == 4 else -1
            parts = [self.sentence(category, pol) for _ in range(n - 1)]
            parts.append(self.contrast(category, -pol, pol) if self.rng.random() < 0.6
                         else self.sentence(category, 0))
        else:  # 3 stars: mixed or plainly neutral
            for _ in range(n):
                r = self.rng.random()
                if r < 0.4:
                    parts.append(self.sentence(category, 0))
                elif r < 0.75:
                    parts.append(self.contrast(category, *self.pick([(1, -1), (-1, 1)])))
                else:
                    parts.append(self.sentence(category, self.pick([1, -1])))
        closers = {1: NEG_CLOSERS, 2: NEG_CLOSERS, 3: NEU_CLOSERS, 4: POS_CLOSERS, 5: POS_CLOSERS}
        if self.rng.random() < 0.6:
            parts.append(self.pick(closers[stars]))
        return " ".join(parts)

    def corrupt(self, text: str) -> str:
        """Add realistic noise: umlaut transliteration, typos, lower-casing."""
        if self.rng.random() < 0.12:
            text = (text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
                    .replace("ß", "ss"))
        if self.rng.random() < 0.15:
            chars = list(text)
            for _ in range(int(self.rng.integers(1, 3))):
                i = int(self.rng.integers(1, len(chars) - 2))
                if chars[i].isalpha() and chars[i + 1].isalpha():
                    chars[i], chars[i + 1] = chars[i + 1], chars[i]
            text = "".join(chars)
        if self.rng.random() < 0.08:
            text = text.lower()
        return text


def generate_reviews(n: int = 6000, seed: int = 42, label_noise: float = 0.03) -> pd.DataFrame:
    """Generate ``n`` synthetic reviews with columns review_id, category, stars, text, label.

    ``label_noise`` is the share of reviews whose star rating is replaced by a random one,
    mimicking customers whose text and rating disagree.
    """
    rng = np.random.default_rng(seed)
    g = _Gen(rng)
    cats = list(CATEGORIES)
    rows = []
    for i in range(n):
        category = g.pick(cats)
        stars = int(rng.choice(np.arange(1, 6), p=STAR_PROBS))
        text = g.corrupt(g.review(category, stars))
        if rng.random() < label_noise:
            stars = int(rng.integers(1, 6))
        rows.append({"review_id": i, "category": category, "stars": stars,
                     "text": text, "label": star_to_label(stars)})
    return pd.DataFrame(rows)


def train_val_test_split(
    df: pd.DataFrame, val_size: float = 0.15, test_size: float = 0.15, seed: int = 42
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Stratified (by label) split into train / validation / test."""
    rng = np.random.default_rng(seed)
    parts: dict[str, list[pd.DataFrame]] = {"train": [], "val": [], "test": []}
    for _, grp in df.groupby("label", sort=True):
        idx = rng.permutation(grp.index.to_numpy())
        n_test = round(len(idx) * test_size)
        n_val = round(len(idx) * val_size)
        parts["test"].append(df.loc[idx[:n_test]])
        parts["val"].append(df.loc[idx[n_test:n_test + n_val]])
        parts["train"].append(df.loc[idx[n_test + n_val:]])
    out = [pd.concat(parts[k]).sort_values("review_id").reset_index(drop=True)
           for k in ("train", "val", "test")]
    return out[0], out[1], out[2]
