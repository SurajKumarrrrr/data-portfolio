"""Optional: fine-tune a pre-trained German model on the same split.

NOT part of CI and NOT used for the README numbers - it needs internet access to the
Hugging Face Hub and is slow on CPU. Usage::

    pip install "transformers>=4.40,<5"
    python scripts/finetune_pretrained.py --model distilbert-base-german-cased --epochs 2

It reuses the generator, split and metrics of the main pipeline so the numbers are directly
comparable with ``reports/results.json``.
"""

from __future__ import annotations

import argparse
import json

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from gersent.data import LABELS, generate_reviews, train_val_test_split
from gersent.evaluate import compute_metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="distilbert-base-german-cased")
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=3e-5)
    args = parser.parse_args()

    torch.manual_seed(42)
    train, _, test = train_val_test_split(generate_reviews(6000, seed=42), seed=42)
    tok = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForSequenceClassification.from_pretrained(args.model,
                                                               num_labels=len(LABELS))
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)

    def batches(df, shuffle: bool):
        df = df.sample(frac=1, random_state=42) if shuffle else df
        for i in range(0, len(df), args.batch_size):
            chunk = df.iloc[i:i + args.batch_size]
            enc = tok(chunk["text"].tolist(), truncation=True, max_length=128,
                      padding=True, return_tensors="pt")
            labels = torch.tensor([LABELS.index(lbl) for lbl in chunk["label"]])
            yield enc, labels

    for epoch in range(args.epochs):
        model.train()
        for enc, labels in batches(train, shuffle=True):
            opt.zero_grad()
            loss = model(**enc, labels=labels).loss
            loss.backward()
            opt.step()
        print(f"epoch {epoch + 1} done, last loss {loss.item():.4f}")

    model.eval()
    preds: list[str] = []
    with torch.no_grad():
        for enc, _ in batches(test, shuffle=False):
            preds += [LABELS[i] for i in model(**enc).logits.argmax(-1).tolist()]
    print(json.dumps(compute_metrics(test["label"].tolist(), preds), indent=2))


if __name__ == "__main__":
    main()
