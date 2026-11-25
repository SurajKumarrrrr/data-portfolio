"""A small Transformer encoder classifier trained from scratch with PyTorch.

Why from scratch and not a pre-trained ``bert-base-german-cased``? The project must run
offline and in CI in a couple of minutes. ``scripts/finetune_pretrained.py`` shows the
fine-tuning path for a pre-trained German model when internet access is available.
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass

import numpy as np
import torch
from sklearn.metrics import f1_score
from torch import nn

from gersent.data import LABELS
from gersent.vocab import Vocab


@dataclass
class TransformerConfig:
    d_model: int = 64
    n_heads: int = 4
    n_layers: int = 2
    ff_dim: int = 128
    dropout: float = 0.1
    max_len: int = 96
    lr: float = 2e-3
    weight_decay: float = 0.01
    batch_size: int = 64
    max_epochs: int = 12
    patience: int = 3
    seed: int = 42


class TinyTransformerClassifier(nn.Module):
    """Token + learned positional embeddings -> TransformerEncoder -> [CLS] -> linear."""

    def __init__(self, vocab_size: int, n_classes: int, cfg: TransformerConfig) -> None:
        super().__init__()
        self.tok = nn.Embedding(vocab_size, cfg.d_model, padding_idx=0)
        self.pos = nn.Embedding(cfg.max_len, cfg.d_model)
        layer = nn.TransformerEncoderLayer(
            d_model=cfg.d_model, nhead=cfg.n_heads, dim_feedforward=cfg.ff_dim,
            dropout=cfg.dropout, batch_first=True, norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=cfg.n_layers,
                                             enable_nested_tensor=False)
        self.norm = nn.LayerNorm(cfg.d_model)
        self.head = nn.Linear(cfg.d_model, n_classes)

    def forward(self, ids: torch.Tensor) -> torch.Tensor:
        positions = torch.arange(ids.size(1), device=ids.device).unsqueeze(0)
        x = self.tok(ids) + self.pos(positions)
        x = self.encoder(x, src_key_padding_mask=ids.eq(0))
        return self.head(self.norm(x[:, 0]))  # [CLS] token representation


def _set_seed(seed: int) -> None:
    torch.manual_seed(seed)
    np.random.seed(seed)


def _encode(vocab: Vocab, texts: list[str], max_len: int) -> torch.Tensor:
    return torch.tensor([vocab.encode(t, max_len) for t in texts], dtype=torch.long)


class TransformerSentiment:
    """scikit-learn-like wrapper: ``fit(texts, labels, val_texts, val_labels)`` / ``predict``."""

    def __init__(self, cfg: TransformerConfig | None = None) -> None:
        self.cfg = cfg or TransformerConfig()
        self.labels = list(LABELS)
        self.vocab: Vocab | None = None
        self.model: TinyTransformerClassifier | None = None
        self.history: list[dict[str, float]] = []

    def fit(self, texts: list[str], labels: list[str],
            val_texts: list[str], val_labels: list[str]) -> TransformerSentiment:
        cfg = self.cfg
        _set_seed(cfg.seed)
        torch.set_num_threads(min(4, torch.get_num_threads()))
        self.vocab = Vocab.build(texts)
        self.model = TinyTransformerClassifier(len(self.vocab), len(self.labels), cfg)

        x = _encode(self.vocab, texts, cfg.max_len)
        y = torch.tensor([self.labels.index(lbl) for lbl in labels])
        counts = torch.bincount(y, minlength=len(self.labels)).float()
        weights = counts.sum() / (len(self.labels) * counts.clamp(min=1))  # "balanced"
        loss_fn = nn.CrossEntropyLoss(weight=weights)
        opt = torch.optim.AdamW(self.model.parameters(), lr=cfg.lr,
                                weight_decay=cfg.weight_decay)
        gen = torch.Generator().manual_seed(cfg.seed)

        best_f1, best_state, bad_epochs = -1.0, None, 0
        for epoch in range(1, cfg.max_epochs + 1):
            self.model.train()
            perm = torch.randperm(len(x), generator=gen)
            total = 0.0
            for start in range(0, len(x), cfg.batch_size):
                idx = perm[start:start + cfg.batch_size]
                opt.zero_grad()
                loss = loss_fn(self.model(x[idx]), y[idx])
                loss.backward()
                nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                opt.step()
                total += loss.item() * len(idx)
            val_f1 = f1_score(val_labels, self.predict(val_texts), average="macro")
            self.history.append({"epoch": epoch, "train_loss": total / len(x),
                                 "val_macro_f1": float(val_f1)})
            if val_f1 > best_f1:
                best_f1, best_state, bad_epochs = val_f1, copy.deepcopy(
                    self.model.state_dict()), 0
            else:
                bad_epochs += 1
                if bad_epochs >= cfg.patience:
                    break
        if best_state is not None:
            self.model.load_state_dict(best_state)
        return self

    @torch.no_grad()
    def predict_proba(self, texts: list[str]) -> np.ndarray:
        if self.model is None or self.vocab is None:
            raise RuntimeError("Model is not fitted")
        self.model.eval()
        x = _encode(self.vocab, texts, self.cfg.max_len)
        out = [torch.softmax(self.model(x[i:i + 256]), dim=-1) for i in range(0, len(x), 256)]
        return torch.cat(out).numpy()

    def predict(self, texts: list[str]) -> list[str]:
        return [self.labels[i] for i in self.predict_proba(texts).argmax(axis=1)]

    def n_parameters(self) -> int:
        return sum(p.numel() for p in self.model.parameters()) if self.model else 0

    def config_dict(self) -> dict:
        return asdict(self.cfg)
