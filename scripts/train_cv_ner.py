# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Train a local CV token-classification model.

Expected input format: JSONL with one sample per line.

{
  "text": "Jane Doe ...",
  "entities": [
    {"start": 0, "end": 8, "label": "NAME"},
    {"start": 42, "end": 48, "label": "SKILL"}
  ]
}

The script writes a Hugging Face checkpoint that can be loaded by
``src.services.cv_ner.CvNerModel``.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:  # pragma: no cover - optional dependency
    import torch
    from torch.utils.data import DataLoader, Dataset
    from transformers import AdamW, AutoModelForTokenClassification, AutoTokenizer, get_linear_schedule_with_warmup
except ImportError as exc:  # pragma: no cover - optional dependency
    raise SystemExit(
        "Training requires torch and transformers to be installed in the local environment."
    ) from exc


@dataclass(frozen=True)
class EntitySpan:
    start: int
    end: int
    label: str


@dataclass(frozen=True)
class TrainingSample:
    text: str
    entities: list[EntitySpan]


class CVDataset(Dataset):
    def __init__(self, samples: list[TrainingSample], tokenizer, label2id: dict[str, int], max_length: int = 512) -> None:
        self.samples = samples
        self.tokenizer = tokenizer
        self.label2id = label2id
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        sample = self.samples[index]
        encoding = self.tokenizer(
            sample.text,
            truncation=True,
            max_length=self.max_length,
            return_offsets_mapping=True,
            padding="max_length",
        )
        offsets = encoding.pop("offset_mapping")
        labels = [-100] * len(encoding["input_ids"])
        for entity in sample.entities:
            started = False
            for token_index, (start, end) in enumerate(offsets):
                if start == end == 0:
                    continue
                if end <= entity.start or start >= entity.end:
                    continue
                prefix = "B-" if not started else "I-"
                labels[token_index] = self.label2id[f"{prefix}{entity.label}"]
                started = True
        encoding["labels"] = labels
        return {key: torch.tensor(value) for key, value in encoding.items()}


def _load_samples(path: Path) -> list[TrainingSample]:
    samples: list[TrainingSample] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            text = str(payload.get("text") or "").strip()
            if not text:
                continue
            entities = [
                EntitySpan(start=int(item["start"]), end=int(item["end"]), label=str(item["label"]).upper())
                for item in payload.get("entities") or []
                if item.get("label") and int(item.get("end", 0)) > int(item.get("start", 0))
            ]
            samples.append(TrainingSample(text=text, entities=entities))
    if not samples:
        raise SystemExit(f"No training samples found in {path}")
    return samples


def _build_label_space(samples: list[TrainingSample]) -> dict[str, int]:
    base_labels = {"O"}
    for sample in samples:
        for entity in sample.entities:
            base_labels.add(f"B-{entity.label}")
            base_labels.add(f"I-{entity.label}")
    labels = ["O"] + sorted(label for label in base_labels if label != "O")
    return {label: index for index, label in enumerate(labels)}


def train(args: argparse.Namespace) -> None:
    samples = _load_samples(Path(args.train_jsonl))
    if args.eval_jsonl:
        eval_samples = _load_samples(Path(args.eval_jsonl))
    else:
        eval_samples = []

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, local_files_only=not args.allow_download)
    label2id = _build_label_space(samples + eval_samples)
    id2label = {index: label for label, index in label2id.items()}
    model = AutoModelForTokenClassification.from_pretrained(
        args.base_model,
        local_files_only=not args.allow_download,
        num_labels=len(label2id),
        id2label=id2label,
        label2id=label2id,
    )

    train_dataset = CVDataset(samples, tokenizer, label2id, max_length=args.max_length)
    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)
    eval_loader = DataLoader(
        CVDataset(eval_samples, tokenizer, label2id, max_length=args.max_length),
        batch_size=args.batch_size,
        shuffle=False,
    ) if eval_samples else None

    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    model.to(device)
    optimizer = AdamW(model.parameters(), lr=args.learning_rate)
    total_steps = max(len(train_loader) * args.epochs, 1)
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=max(total_steps // 10, 1),
        num_training_steps=total_steps,
    )

    model.train()
    for epoch in range(args.epochs):
        for batch in train_loader:
            batch = {key: value.to(device) for key, value in batch.items()}
            outputs = model(**batch)
            loss = outputs.loss
            loss.backward()
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
        if eval_loader:
            _evaluate(model, eval_loader, device)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)


def _evaluate(model, loader, device) -> None:
    model.eval()
    with torch.no_grad():
        for batch in loader:
            batch = {key: value.to(device) for key, value in batch.items()}
            model(**batch)
    model.train()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train a local CV NER model.")
    parser.add_argument("--train-jsonl", required=True, help="Training annotations in JSONL format.")
    parser.add_argument("--eval-jsonl", help="Optional evaluation annotations in JSONL format.")
    parser.add_argument("--output-dir", required=True, help="Directory where the checkpoint will be saved.")
    parser.add_argument("--base-model", default="camembert-base", help="Backbone model name.")
    parser.add_argument("--max-length", type=int, default=512, help="Maximum token length.")
    parser.add_argument("--batch-size", type=int, default=4, help="Training batch size.")
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs.")
    parser.add_argument("--learning-rate", type=float, default=5e-5, help="AdamW learning rate.")
    parser.add_argument("--cpu", action="store_true", help="Force CPU training.")
    parser.add_argument(
        "--allow-download",
        action="store_true",
        help="Allow downloading the base model if it is not already cached locally.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    train(args)


if __name__ == "__main__":
    main()
