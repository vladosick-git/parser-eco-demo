"""Чтение и запись JSON и CSV в папке data/."""

import csv
import json
import os
from pathlib import Path

NEWS_CSV_FIELDS = ["published", "source_name", "category", "title", "summary", "url"]
WASTE_CSV_FIELDS = [
    "published", "source_name", "offer_type", "category", "title", "fkko", "hazard_classes",
    "volume", "volume_unit", "price", "currency", "region", "organization", "url",
]


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save_json(path: Path, data) -> None:
    """Атомарная запись: сначала во временный файл, потом замена."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def save_bundle(path: Path, data: dict) -> None:
    path.write_text("window.ECO_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n", encoding="utf-8")


def save_csv(path: Path, items: list[dict], fields: list[str]) -> None:
    """CSV в UTF-8 с BOM, чтобы Excel сразу открыл кириллицу."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", delimiter=";")
        writer.writeheader()
        for item in items:
            row = dict(item)
            if isinstance(row.get("hazard_classes"), list):
                row["hazard_classes"] = ",".join(map(str, row["hazard_classes"]))
            writer.writerow(row)
