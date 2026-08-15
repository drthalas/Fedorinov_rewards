#!/usr/bin/env python3
"""Read-only managed-media inventory and JPEG sizing forecast.

The analyzer never writes below ``--data-root`` and opens SQLite in immutable,
read-only mode. JPEG forecasts are encoded into memory and discarded.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sqlite3
import statistics
import sys
import threading
import time
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Iterable, Sequence
from urllib.parse import quote, unquote

from PIL import Image, UnidentifiedImageError


MANAGED_ROOTS = ("Source", "SourceMark", "default", "GuideImages")
REFERENCE_COLUMNS = {
    "person": (
        "person_foto",
        "main_foto",
        "rewards_foto",
        "book1_foto",
        "book2_foto",
        "card1_foto",
        "card2_foto",
    ),
    "rewards": ("front_foto", "back_foto", "book1_foto", "book2_foto", "reward_list"),
    "mark": ("front_foto", "back_foto", "book1_foto", "book2_foto"),
    "person_media": ("file_path",),
    "guide": ("image_path",),
    "guide_lev_0": ("image_path",),
    "guide_lev_1": ("image_path",),
    "guide_lev_2": ("image_path",),
    "guide_lev_3": ("image_path",),
    "guide_lev_4": ("image_path",),
}
RASTER_EXTENSION_FORMATS = {
    ".bmp": "BMP",
    ".gif": "GIF",
    ".jfif": "JPEG",
    ".jp2": "JPEG2000",
    ".jpe": "JPEG",
    ".jpeg": "JPEG",
    ".jpg": "JPEG",
    ".png": "PNG",
    ".tif": "TIFF",
    ".tiff": "TIFF",
    ".webp": "WEBP",
}
NON_RASTER_EXTENSIONS = {
    ".doc",
    ".docx",
    ".ini",
    ".pdf",
    ".ppt",
    ".pptx",
    ".ttf",
    ".xls",
    ".xlsx",
}
JPEG_CANDIDATE_MIN_BYTES = 64 * 1024
JPEG_CANDIDATE_MIN_DIMENSION = 256
JPEG_MAX_DIMENSION = 65_500
PHOTO_LIKE_MIN_COLORS = 1024
DEFAULT_QUALITIES = (88, 90, 92)
DEFAULT_ESTIMATE_SAMPLE_SIZE = 1200
JPEG_PROFILE_SETTINGS = {
    "optimize": False,
    "progressive": False,
    "subsampling": 0,
}


@dataclass(frozen=True)
class FileEntry:
    path: Path
    relative_path: str
    size: int
    mtime_ns: int


class MemorySampler:
    def __init__(self, interval_seconds: float = 0.25) -> None:
        self.interval_seconds = interval_seconds
        self.samples: list[int] = []
        self.native_peak_samples: list[int] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="memory-sampler", daemon=True)

    def __enter__(self) -> "MemorySampler":
        self._sample()
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self._sample()

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self._sample()

    def _sample(self) -> None:
        current, native_peak = process_memory_bytes()
        if current is not None:
            self.samples.append(current)
        if native_peak is not None:
            self.native_peak_samples.append(native_peak)

    def summary(self) -> dict[str, int | None]:
        if not self.samples:
            return {"typical_rss_bytes": None, "peak_rss_bytes": None, "samples": 0}
        return {
            "typical_rss_bytes": int(statistics.median(self.samples)),
            "peak_rss_bytes": max(self.native_peak_samples or self.samples),
            "samples": len(self.samples),
        }


def process_memory_bytes() -> tuple[int | None, int | None]:
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                    ("PrivateUsage", ctypes.c_size_t),
                ]

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = (
                wintypes.HANDLE,
                ctypes.POINTER(ProcessMemoryCounters),
                wintypes.DWORD,
            )
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            process = kernel32.GetCurrentProcess()
            ok = psapi.GetProcessMemoryInfo(
                process,
                ctypes.byref(counters),
                counters.cb,
            )
            if not ok:
                return None, None
            return int(counters.WorkingSetSize), int(counters.PeakWorkingSetSize)
        except (AttributeError, OSError, ValueError):
            return None, None
    try:
        import resource

        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak = int(rss if sys.platform == "darwin" else rss * 1024)
        return peak, peak
    except (ImportError, ValueError):
        return None, None


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _fingerprint_rows(rows: Iterable[tuple[str, int, int]]) -> str:
    digest = hashlib.sha256()
    for relative_path, size, mtime_ns in rows:
        digest.update(relative_path.encode("utf-8", "surrogatepass"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        digest.update(str(mtime_ns).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def inventory_files(data_root: Path) -> list[FileEntry]:
    files: list[FileEntry] = []
    for root_name in MANAGED_ROOTS:
        root = data_root / root_name
        if not root.exists():
            continue
        for directory, directory_names, file_names in os.walk(root, followlinks=False):
            directory_names.sort(key=str.casefold)
            file_names.sort(key=str.casefold)
            for file_name in file_names:
                path = Path(directory) / file_name
                if path.is_symlink():
                    continue
                stat = path.stat()
                relative = path.relative_to(data_root).as_posix()
                files.append(FileEntry(path, relative, stat.st_size, stat.st_mtime_ns))
    return sorted(files, key=lambda item: (item.relative_path.casefold(), item.relative_path))


def metadata_fingerprint(files: Sequence[FileEntry]) -> str:
    return _fingerprint_rows((item.relative_path, item.size, item.mtime_ns) for item in files)


def readonly_connection(database: Path) -> sqlite3.Connection:
    uri_path = quote(database.resolve().as_posix(), safe="/:~")
    connection = sqlite3.connect(f"file:{uri_path}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("pragma query_only = on")
    return connection


def quoted_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def normalize_reference(raw_value: object) -> tuple[str | None, str]:
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None, "empty"
    value = unquote(raw_value).strip().strip('"').strip("'").replace("\\", "/")
    windows_path = PureWindowsPath(value)
    parts = [part for part in windows_path.parts if part not in {windows_path.anchor, "", "/"}]
    lowered_roots = {root.casefold(): root for root in MANAGED_ROOTS}
    root_index = next((index for index, part in enumerate(parts) if part.casefold() in lowered_roots), None)
    if root_index is None:
        return None, "external_or_unsupported"
    relative_parts = parts[root_index:]
    if any(part in {".", ".."} for part in relative_parts):
        return None, "path_traversal"
    relative_parts[0] = lowered_roots[relative_parts[0].casefold()]
    return "/".join(relative_parts), "managed"


def load_references(database: Path) -> tuple[Counter[str], dict[str, object]]:
    references: Counter[str] = Counter()
    invalid = Counter()
    inspected_columns: list[str] = []
    raw_count = 0
    with closing(readonly_connection(database)) as connection:
        table_rows = connection.execute("select name from sqlite_master where type = 'table'").fetchall()
        tables = {row["name"] for row in table_rows}
        for table, desired_columns in REFERENCE_COLUMNS.items():
            if table not in tables:
                continue
            info = connection.execute(f"pragma table_info({quoted_identifier(table)})").fetchall()
            columns = {row["name"] for row in info}
            for column in desired_columns:
                if column not in columns:
                    continue
                inspected_columns.append(f"{table}.{column}")
                query = (
                    f"select {quoted_identifier(column)} as media_path "
                    f"from {quoted_identifier(table)} where {quoted_identifier(column)} is not null"
                )
                for row in connection.execute(query):
                    raw_count += 1
                    normalized, state = normalize_reference(row["media_path"])
                    if normalized is None:
                        invalid[state] += 1
                    else:
                        references[normalized.casefold()] += 1
    return references, {
        "raw_reference_count": raw_count,
        "normalized_reference_count": sum(references.values()),
        "unique_normalized_paths": len(references),
        "invalid_or_external": dict(sorted(invalid.items())),
        "inspected_columns": sorted(inspected_columns),
        "database_open_mode": "mode=ro&immutable=1; PRAGMA query_only=ON",
    }


def extension_matches(actual_format: str | None, extension: str) -> bool | None:
    expected = RASTER_EXTENSION_FORMATS.get(extension.casefold())
    if expected is None:
        return None
    if expected == "JPEG" and actual_format == "MPO":
        return True
    return expected == actual_format


def alpha_state(image: Image.Image) -> tuple[bool, bool]:
    has_alpha_channel = "A" in image.getbands() or "transparency" in image.info
    if not has_alpha_channel:
        return False, False
    try:
        alpha = image.convert("RGBA").getchannel("A")
        extrema = alpha.getextrema()
        return True, bool(extrema and extrema[0] < 255)
    except (OSError, ValueError):
        return True, True


def photo_like(image: Image.Image) -> bool:
    sample = image.convert("RGB")
    sample.thumbnail((256, 256))
    return sample.getcolors(maxcolors=PHOTO_LIKE_MIN_COLORS) is None


def classify_png(
    image: Image.Image,
    source_bytes: int,
    has_alpha_channel: bool,
    has_transparency: bool,
) -> tuple[str, str]:
    if has_transparency:
        return "keep_lossless_alpha", "actual_transparency"
    if image.mode not in {"RGB", "RGBA"}:
        return "keep_lossless_other", f"non_rgb_mode:{image.mode}"
    if source_bytes < JPEG_CANDIDATE_MIN_BYTES:
        return "keep_lossless_other", "small_source"
    if min(image.size) < JPEG_CANDIDATE_MIN_DIMENSION:
        return "keep_lossless_other", "small_dimension"
    if max(image.size) > JPEG_MAX_DIMENSION:
        return "keep_lossless_other", "jpeg_dimension_limit"
    if not photo_like(image):
        return "keep_lossless_other", "limited_color_graphic_or_document"
    reason = "opaque_photo_like_rgba_png" if has_alpha_channel else "opaque_photo_like_rgb_png"
    return "jpeg_candidate", reason


def inspect_file(entry: FileEntry, reference_count: int) -> dict[str, object]:
    extension = entry.path.suffix.casefold()
    checksum = sha256_file(entry.path)
    record: dict[str, object] = {
        "relative_path": entry.relative_path,
        "source_bytes": entry.size,
        "source_mtime_ns": entry.mtime_ns,
        "source_sha256": checksum,
        "extension": extension,
        "reference_count": reference_count,
        "actual_format": None,
        "width": None,
        "height": None,
        "mode": None,
        "has_alpha_channel": False,
        "has_transparency": False,
        "decode_status": "not_raster",
        "extension_matches_content": None,
        "classification": "non_raster_out_of_scope",
        "classification_reason": "non_raster_extension",
    }
    try:
        with Image.open(entry.path) as image:
            actual_format = (image.format or "UNKNOWN").upper()
            image.load()
            has_alpha_channel, has_transparency = alpha_state(image)
            record.update(
                {
                    "actual_format": actual_format,
                    "width": image.width,
                    "height": image.height,
                    "mode": image.mode,
                    "has_alpha_channel": has_alpha_channel,
                    "has_transparency": has_transparency,
                    "decode_status": "decoded",
                    "extension_matches_content": extension_matches(actual_format, extension),
                }
            )
            if actual_format == "PNG":
                classification, reason = classify_png(
                    image,
                    entry.size,
                    has_alpha_channel,
                    has_transparency,
                )
            elif actual_format in {"JPEG", "WEBP"}:
                classification, reason = "already_optimized", actual_format.casefold()
            else:
                classification, reason = "other_raster_keep", actual_format.casefold()
            record["classification"] = classification
            record["classification_reason"] = reason
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        if extension in NON_RASTER_EXTENSIONS:
            record["classification_reason"] = "known_non_raster_extension"
        else:
            record["decode_status"] = "corrupt_or_unsupported"
            record["classification"] = "corrupt_or_unsupported"
            record["classification_reason"] = type(exc).__name__
            record["extension_matches_content"] = False if extension in RASTER_EXTENSION_FORMATS else None
    return record


def deterministic_sample(records: Sequence[dict[str, object]], sample_size: int) -> list[dict[str, object]]:
    if sample_size <= 0:
        return []
    if len(records) <= sample_size:
        return list(records)
    ordered = sorted(records, key=lambda item: (int(item["source_bytes"]), str(item["relative_path"])))
    bucket_count = min(10, len(ordered))
    selected: list[dict[str, object]] = []
    for bucket_index in range(bucket_count):
        start = len(ordered) * bucket_index // bucket_count
        end = len(ordered) * (bucket_index + 1) // bucket_count
        bucket = ordered[start:end]
        target = sample_size // bucket_count + (1 if bucket_index < sample_size % bucket_count else 0)
        ranked = sorted(
            bucket,
            key=lambda item: hashlib.sha256(str(item["relative_path"]).encode("utf-8")).digest(),
        )
        selected.extend(ranked[:target])
    return selected


def encode_jpeg_sizes(path: Path, qualities: Sequence[int]) -> dict[int, int]:
    with Image.open(path) as image:
        image.load()
        rgb = image.convert("RGB")
        sizes: dict[int, int] = {}
        for quality in qualities:
            output = io.BytesIO()
            rgb.save(output, format="JPEG", quality=quality, **JPEG_PROFILE_SETTINGS)
            sizes[quality] = output.tell()
        return sizes


def quality_forecasts(
    data_root: Path,
    candidates: Sequence[dict[str, object]],
    total_media_bytes: int,
    qualities: Sequence[int],
    sample_size: int,
) -> tuple[dict[str, object], set[str]]:
    sampled = deterministic_sample(candidates, sample_size)
    encoded: dict[str, dict[int, int]] = {}
    encoding_errors = 0
    for record in sampled:
        relative_path = str(record["relative_path"])
        try:
            encoded[relative_path] = encode_jpeg_sizes(data_root / Path(relative_path), qualities)
        except (OSError, ValueError, MemoryError):
            encoding_errors += 1

    successfully_sampled = [item for item in sampled if str(item["relative_path"]) in encoded]

    candidate_source_bytes = sum(int(item["source_bytes"]) for item in candidates)
    forecasts: dict[str, object] = {}
    for quality in qualities:
        sampled_source = sum(int(item["source_bytes"]) for item in successfully_sampled)
        sampled_target = sum(
            min(encoded[str(item["relative_path"])][quality], int(item["source_bytes"]))
            for item in successfully_sampled
        )
        smaller_count = sum(
            encoded[str(item["relative_path"])][quality] < int(item["source_bytes"])
            for item in successfully_sampled
        )
        ratio = sampled_target / sampled_source if sampled_source else 1.0
        predicted_candidate_bytes = round(candidate_source_bytes * ratio)
        predicted_total_bytes = total_media_bytes - candidate_source_bytes + predicted_candidate_bytes
        predicted_converted_count = (
            round(len(candidates) * smaller_count / len(successfully_sampled)) if successfully_sampled else 0
        )
        saved_bytes = total_media_bytes - predicted_total_bytes
        forecasts[str(quality)] = {
            "eligible_candidate_count": len(candidates),
            "sampled_candidate_count": len(successfully_sampled),
            "sample_encoding_errors": encoding_errors,
            "sampled_source_bytes": sampled_source,
            "sampled_encoded_or_source_bytes": sampled_target,
            "sampled_smaller_count": smaller_count,
            "predicted_converted_file_count": predicted_converted_count,
            "predicted_total_bytes": predicted_total_bytes,
            "predicted_saved_bytes": saved_bytes,
            "predicted_saved_percent": (saved_bytes * 100 / total_media_bytes) if total_media_bytes else 0.0,
            "jpeg_settings": dict(JPEG_PROFILE_SETTINGS),
        }
    return forecasts, set(encoded)


def classification_digest(records: Sequence[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    keys = (
        "relative_path",
        "source_bytes",
        "source_sha256",
        "actual_format",
        "width",
        "height",
        "mode",
        "has_alpha_channel",
        "has_transparency",
        "decode_status",
        "extension_matches_content",
        "classification",
        "classification_reason",
        "reference_count",
    )
    for record in records:
        stable = {key: record.get(key) for key in keys}
        digest.update(json.dumps(stable, ensure_ascii=True, sort_keys=True).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def summarize_records(records: Sequence[dict[str, object]]) -> dict[str, object]:
    format_counts: Counter[str] = Counter()
    format_bytes: Counter[str] = Counter()
    classifications: Counter[str] = Counter()
    classification_bytes: Counter[str] = Counter()
    mismatches = 0
    corrupt = 0
    referenced_files = 0
    png_alpha_channel_count = 0
    png_alpha_channel_bytes = 0
    png_transparency_count = 0
    png_transparency_bytes = 0
    for record in records:
        actual_format = record.get("actual_format")
        if actual_format:
            format_counts[str(actual_format)] += 1
            format_bytes[str(actual_format)] += int(record["source_bytes"])
        classifications[str(record["classification"])] += 1
        classification_bytes[str(record["classification"])] += int(record["source_bytes"])
        if record.get("extension_matches_content") is False and record.get("decode_status") == "decoded":
            mismatches += 1
        if record.get("decode_status") == "corrupt_or_unsupported":
            corrupt += 1
        if int(record["reference_count"]):
            referenced_files += 1
        if actual_format == "PNG" and record.get("has_alpha_channel"):
            png_alpha_channel_count += 1
            png_alpha_channel_bytes += int(record["source_bytes"])
        if actual_format == "PNG" and record.get("has_transparency"):
            png_transparency_count += 1
            png_transparency_bytes += int(record["source_bytes"])
    return {
        "actual_formats": {
            key: {"files": format_counts[key], "bytes": format_bytes[key]}
            for key in sorted(format_counts)
        },
        "classifications": {
            key: {"files": classifications[key], "bytes": classification_bytes[key]}
            for key in sorted(classifications)
        },
        "mismatched_extension_content_files": mismatches,
        "corrupt_or_unsupported_files": corrupt,
        "referenced_files": referenced_files,
        "unreferenced_files": len(records) - referenced_files,
        "png_alpha": {
            "alpha_channel_files": png_alpha_channel_count,
            "alpha_channel_bytes": png_alpha_channel_bytes,
            "actual_transparency_files": png_transparency_count,
            "actual_transparency_bytes": png_transparency_bytes,
            "opaque_alpha_channel_files": png_alpha_channel_count - png_transparency_count,
            "opaque_alpha_channel_bytes": png_alpha_channel_bytes - png_transparency_bytes,
        },
    }


def write_reports(output_dir: Path, records: Sequence[dict[str, object]], summary: dict[str, object]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "media_manifest.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "summary.md").write_text(render_markdown(summary), encoding="utf-8")


def render_markdown(summary: dict[str, object]) -> str:
    inventory = summary["inventory"]
    record_summary = summary["records"]
    lines = [
        "# Managed media read-only baseline",
        "",
        f"- Files: {inventory['files']:,}",
        f"- Bytes: {inventory['bytes']:,}",
        f"- GiB: {inventory['gib']:.3f}",
        f"- Classification digest: `{summary['classification_digest']}`",
        f"- Scan seconds: {summary['performance']['total_seconds']:.3f}",
        "",
        "## Actual formats",
        "",
        "| Format | Files | Bytes |",
        "| --- | ---: | ---: |",
    ]
    for image_format, values in record_summary["actual_formats"].items():
        lines.append(f"| {image_format} | {values['files']:,} | {values['bytes']:,} |")
    lines.extend(["", "## JPEG forecasts", "", "| Quality | Converted files | Saved GiB | Saved % |", "| ---: | ---: | ---: | ---: |"])
    for quality, values in summary["quality_forecasts"].items():
        lines.append(
            f"| {quality} | {values['predicted_converted_file_count']:,} | "
            f"{values['predicted_saved_bytes'] / (1024 ** 3):.3f} | {values['predicted_saved_percent']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Safety",
            "",
            f"- Database unchanged: {summary['safety']['database_unchanged']}",
            f"- Media metadata fingerprint unchanged: {summary['safety']['media_metadata_unchanged']}",
            f"- SQLite mode: {summary['references']['database_open_mode']}",
            f"- Source write operations: {summary['safety']['source_write_operations']}",
            "",
        ]
    )
    return "\n".join(lines)


def ensure_safe_paths(data_root: Path, database: Path, output_dir: Path) -> None:
    data_root = data_root.resolve()
    database = database.resolve()
    output_dir = output_dir.resolve()
    if not data_root.is_dir():
        raise ValueError(f"data root does not exist: {data_root}")
    if not database.is_file():
        raise ValueError(f"database does not exist: {database}")
    if output_dir == data_root or data_root in output_dir.parents:
        raise ValueError("output directory must not be inside the managed data root")


def run_analysis(
    data_root: Path,
    database: Path,
    output_dir: Path,
    qualities: Sequence[int] = DEFAULT_QUALITIES,
    estimate_sample_size: int = DEFAULT_ESTIMATE_SAMPLE_SIZE,
) -> dict[str, object]:
    ensure_safe_paths(data_root, database, output_dir)
    started = time.perf_counter()
    db_before = sha256_file(database)
    files_before = inventory_files(data_root)
    media_before = metadata_fingerprint(files_before)
    references, reference_summary = load_references(database)
    records: list[dict[str, object]] = []

    with MemorySampler() as memory:
        for entry in files_before:
            records.append(inspect_file(entry, references[entry.relative_path.casefold()]))
        candidates = [record for record in records if record["classification"] == "jpeg_candidate"]
        forecasts, sampled_paths = quality_forecasts(
            data_root,
            candidates,
            sum(item.size for item in files_before),
            qualities,
            estimate_sample_size,
        )
        for record in records:
            record["quality_forecast_sampled"] = str(record["relative_path"]) in sampled_paths

    db_after = sha256_file(database)
    files_after = inventory_files(data_root)
    media_after = metadata_fingerprint(files_after)
    record_summary = summarize_records(records)
    present_paths = {item.relative_path.casefold() for item in files_before}
    missing_references = sum(count for path, count in references.items() if path not in present_paths)
    total_bytes = sum(item.size for item in files_before)
    summary: dict[str, object] = {
        "schema_version": 1,
        "mode": "read-only-baseline",
        "inventory": {
            "files": len(files_before),
            "bytes": total_bytes,
            "gib": total_bytes / (1024 ** 3),
            "managed_roots": list(MANAGED_ROOTS),
        },
        "records": record_summary,
        "references": {
            **reference_summary,
            "missing_reference_occurrences": missing_references,
        },
        "classification_policy": {
            "jpeg_candidate": (
                "decoded PNG; RGB or fully opaque RGBA; no actual transparency; >=64 KiB; "
                "both dimensions 256..65500; >=1024 colors in a 256px thumbnail"
            ),
            "keep_lossless_alpha": "PNG with actual non-opaque transparency",
            "quality_estimation": (
                "deterministic size-stratified sample; in-memory baseline JPEG; 4:4:4; "
                "source retained whenever encoded output is not smaller"
            ),
            "checksum": "full SHA-256 for every managed file; aggregate classification digest",
        },
        "quality_forecasts": forecasts,
        "recommended_quality": 90,
        "classification_digest": classification_digest(records),
        "performance": {
            "total_seconds": time.perf_counter() - started,
            **memory.summary(),
        },
        "safety": {
            "database_sha256_before": db_before,
            "database_sha256_after": db_after,
            "database_unchanged": db_before == db_after,
            "media_metadata_fingerprint_before": media_before,
            "media_metadata_fingerprint_after": media_after,
            "media_metadata_unchanged": media_before == media_after,
            "file_count_before": len(files_before),
            "file_count_after": len(files_after),
            "source_write_operations": 0,
            "output_outside_data_root": True,
            "jpeg_forecast_storage": "memory-only BytesIO",
        },
    }
    write_reports(output_dir, records, summary)
    if not summary["safety"]["database_unchanged"] or not summary["safety"]["media_metadata_unchanged"]:
        raise RuntimeError("source DB/media changed during read-only analysis")
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--qualities", nargs="+", type=int, default=list(DEFAULT_QUALITIES))
    parser.add_argument("--estimate-sample-size", type=int, default=DEFAULT_ESTIMATE_SAMPLE_SIZE)
    args = parser.parse_args(argv)
    if any(quality < 1 or quality > 100 for quality in args.qualities):
        parser.error("qualities must be between 1 and 100")
    if args.estimate_sample_size < 0:
        parser.error("estimate sample size must be non-negative")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    summary = run_analysis(
        args.data_root,
        args.database,
        args.output_dir,
        tuple(sorted(set(args.qualities))),
        args.estimate_sample_size,
    )
    print(json.dumps(summary, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
