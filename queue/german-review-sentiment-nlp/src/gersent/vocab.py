"""Word-level vocabulary for the small transformer."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from gersent.text import tokenize

PAD, UNK, CLS = "[PAD]", "[UNK]", "[CLS]"


@dataclass
class Vocab:
    """Maps tokens to integer ids. Id 0 is padding, 1 unknown, 2 the [CLS] token."""

    itos: list[str] = field(default_factory=lambda: [PAD, UNK, CLS])

    def __post_init__(self) -> None:
        self.stoi = {t: i for i, t in enumerate(self.itos)}

    @classmethod
    def build(cls, texts: Iterable[str], min_freq: int = 2, max_size: int = 20000) -> Vocab:
        counts = Counter(tok for text in texts for tok in tokenize(text))
        words = [w for w, c in counts.most_common(max_size) if c >= min_freq]
        return cls([PAD, UNK, CLS, *sorted(words)])

    def __len__(self) -> int:
        return len(self.itos)

    @property
    def pad_id(self) -> int:
        return 0

    def encode(self, text: str, max_len: int = 96) -> list[int]:
        """[CLS] + token ids, truncated to ``max_len`` and right-padded with 0."""
        ids = [self.stoi[CLS]] + [self.stoi.get(t, 1) for t in tokenize(text)]
        ids = ids[:max_len]
        return ids + [0] * (max_len - len(ids))

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.itos, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Vocab:
        return cls(json.loads(path.read_text(encoding="utf-8")))
