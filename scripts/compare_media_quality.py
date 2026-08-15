#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageChops, ImageDraw

from scripts.analyze_managed_media import normalize_reference, quoted_identifier


CATEGORY_FIELDS = {
    "faces_photos": {
        ("person", "person_foto"),
        ("person", "main_foto"),
    },
    "rewards": {
        ("person", "rewards_foto"),
        ("rewards", "front_foto"),
        ("rewards", "back_foto"),
    },
    "scans_documents_text": {
        ("person", "book1_foto"),
        ("person", "book2_foto"),
        ("person", "card1_foto"),
        ("person", "card2_foto"),
        ("rewards", "book1_foto"),
        ("rewards", "book2_foto"),
        ("rewards", "reward_list"),
    },
}
QUALITIES = (88, 90, 92)


def load_manifest(path: Path) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def category_references(database: Path) -> dict[str, set[str]]:
    categories: dict[str, set[str]] = defaultdict(set)
    connection = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        tables = {
            row["name"] for row in connection.execute("select name from sqlite_master where type='table'")
        }
        for category, fields in CATEGORY_FIELDS.items():
            for table, column in fields:
                if table not in tables:
                    continue
                columns = {
                    row["name"]
                    for row in connection.execute(f"pragma table_info({quoted_identifier(table)})")
                }
                if column not in columns:
                    continue
                query = (
                    f"select {quoted_identifier(column)} as media_path from {quoted_identifier(table)} "
                    f"where {quoted_identifier(column)} is not null"
                )
                for row in connection.execute(query):
                    normalized, state = normalize_reference(row["media_path"])
                    if normalized is not None and state == "managed":
                        categories[category].add(normalized.casefold())
    finally:
        connection.close()
    return categories


def deterministic_examples(records: Sequence[dict[str, object]], count: int) -> list[dict[str, object]]:
    if len(records) <= count:
        return list(records)
    ordered = sorted(records, key=lambda item: int(item["source_bytes"]))
    indexes = {round(index * (len(ordered) - 1) / (count - 1)) for index in range(count)}
    return [ordered[index] for index in sorted(indexes)]


def jpeg_bytes(image: Image.Image, quality: int) -> bytes:
    output = io.BytesIO()
    image.convert("RGB").save(
        output,
        format="JPEG",
        quality=quality,
        optimize=False,
        progressive=False,
        subsampling=0,
    )
    return output.getvalue()


def psnr(original: Image.Image, candidate: Image.Image) -> float:
    original_rgb = original.convert("RGB")
    candidate_rgb = candidate.convert("RGB")
    difference = ImageChops.difference(original_rgb, candidate_rgb)
    histogram = difference.histogram()
    squared_error = sum((index % 256) ** 2 * count for index, count in enumerate(histogram))
    samples = original_rgb.width * original_rgb.height * 3
    mse = squared_error / samples if samples else 0
    return 99.0 if mse == 0 else 20 * math.log10(255.0 / math.sqrt(mse))


def _fit(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    copy = image.convert("RGB")
    copy.thumbnail(size)
    canvas = Image.new("RGB", size, (24, 22, 20))
    canvas.paste(copy, ((size[0] - copy.width) // 2, (size[1] - copy.height) // 2))
    return canvas


def _center_crop(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    rgb = image.convert("RGB")
    width = min(size[0], rgb.width)
    height = min(size[1], rgb.height)
    left = max(0, (rgb.width - width) // 2)
    top = max(0, (rgb.height - height) // 2)
    crop = rgb.crop((left, top, left + width, top + height))
    return _fit(crop, size)


def make_sheet(
    data_root: Path,
    category: str,
    records: Sequence[dict[str, object]],
    output_path: Path,
) -> list[dict[str, object]]:
    cell = (320, 220)
    label_height = 28
    columns = 4
    rows_per_sample = 2
    sheet = Image.new(
        "RGB",
        (cell[0] * columns, (cell[1] + label_height) * rows_per_sample * len(records) + 44),
        (20, 18, 16),
    )
    draw = ImageDraw.Draw(sheet)
    draw.text((12, 12), f"{category}: original / Q88 / Q90 / Q92", fill=(230, 205, 150))
    metrics: list[dict[str, object]] = []
    for sample_index, record in enumerate(records):
        path = data_root / Path(str(record["relative_path"]))
        with Image.open(path) as original_source:
            original_source.load()
            original = original_source.convert("RGB")
        versions: list[tuple[str, Image.Image, int, float]] = [("Original", original, int(record["source_bytes"]), 99.0)]
        quality_metrics: dict[str, object] = {}
        for quality in QUALITIES:
            encoded = jpeg_bytes(original, quality)
            with Image.open(io.BytesIO(encoded)) as decoded_source:
                decoded_source.load()
                decoded = decoded_source.convert("RGB")
            value = psnr(original, decoded)
            versions.append((f"Q{quality}", decoded, len(encoded), value))
            quality_metrics[str(quality)] = {
                "bytes": len(encoded),
                "ratio": len(encoded) / int(record["source_bytes"]),
                "psnr": value,
            }
        metrics.append(
            {
                "sample_id": hashlib.sha256(str(record["relative_path"]).encode("utf-8")).hexdigest()[:12],
                "source_bytes": int(record["source_bytes"]),
                "width": int(record["width"]),
                "height": int(record["height"]),
                "qualities": quality_metrics,
            }
        )
        base_y = 44 + sample_index * rows_per_sample * (cell[1] + label_height)
        for column, (label, image, size_bytes, value) in enumerate(versions):
            x = column * cell[0]
            draw.text((x + 8, base_y + 5), f"{label}  {size_bytes / 1024:.0f} KiB  {value:.1f} dB", fill="white")
            sheet.paste(_fit(image, cell), (x, base_y + label_height))
            crop_y = base_y + cell[1] + label_height
            draw.text((x + 8, crop_y + 5), "Center detail", fill=(180, 180, 180))
            sheet.paste(_center_crop(image, cell), (x, crop_y + label_height))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, format="PNG")
    return metrics


def run_comparison(
    data_root: Path,
    database: Path,
    manifest: Path,
    output_dir: Path,
    examples_per_category: int = 3,
) -> dict[str, object]:
    records = load_manifest(manifest)
    categories = category_references(database)
    candidates = {
        str(record["relative_path"]).casefold(): record
        for record in records
        if record.get("classification") == "jpeg_candidate"
    }
    report: dict[str, object] = {"qualities": list(QUALITIES), "categories": {}}
    for category, references in categories.items():
        category_records = [candidates[path] for path in references if path in candidates]
        examples = deterministic_examples(category_records, examples_per_category)
        metrics = make_sheet(data_root, category, examples, output_dir / f"{category}.png") if examples else []
        report["categories"][category] = {
            "candidate_files": len(category_records),
            "candidate_bytes": sum(int(item["source_bytes"]) for item in category_records),
            "examples": metrics,
        }

    graphics = [
        record
        for record in records
        if record.get("actual_format") == "PNG"
        and record.get("classification") == "keep_lossless_other"
    ]
    graphic_examples = deterministic_examples(graphics, examples_per_category)
    graphic_metrics = (
        make_sheet(data_root, "graphics_edges", graphic_examples, output_dir / "graphics_edges.png")
        if graphic_examples
        else []
    )
    alpha = [
        record
        for record in records
        if record.get("actual_format") == "PNG"
        and record.get("classification") == "keep_lossless_alpha"
    ]
    report["categories"]["graphics_edges"] = {
        "files": len(graphics),
        "bytes": sum(int(item["source_bytes"]) for item in graphics),
        "examples": graphic_metrics,
        "reason": "kept lossless to avoid ringing around hard edges and small text",
    }
    report["categories"]["alpha_transparency"] = {
        "files": len(alpha),
        "bytes": sum(int(item["source_bytes"]) for item in alpha),
        "reason": "kept lossless because JPEG cannot preserve alpha",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "quality-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create redacted representative JPEG quality contact sheets.")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--examples-per-category", type=int, default=3)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_comparison(
        args.data_root,
        args.database,
        args.manifest,
        args.output_dir,
        args.examples_per_category,
    )
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
