from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

from PIL import Image, UnidentifiedImageError

from .media_image_policy import JPEG_OPTIONS, JPEG_POLICY_VERSION, JPEG_QUALITY
from .managed_media_analysis import (
    MANAGED_ROOTS,
    REFERENCE_COLUMNS,
    inventory_files,
    metadata_fingerprint,
    normalize_reference,
    quoted_identifier,
    sha256_file,
)


STATUS_FILE = "optimization-status.json"
CONVERSION_MANIFEST = "conversion-manifest.jsonl"
HEALTH_REPORT = "health-report.json"
COMPLETE_MARKER = ".optimization-complete"
INCOMPLETE_MARKER = ".optimization-incomplete"


@dataclass(frozen=True)
class ConversionPolicy:
    version: str = JPEG_POLICY_VERSION
    jpeg_quality: int = JPEG_QUALITY
    optimize: bool = bool(JPEG_OPTIONS["optimize"])
    progressive: bool = bool(JPEG_OPTIONS["progressive"])
    subsampling: int = int(JPEG_OPTIONS["subsampling"])

    def jpeg_options(self) -> dict[str, object]:
        return {
            "quality": self.jpeg_quality,
            "optimize": self.optimize,
            "progressive": self.progressive,
            "subsampling": self.subsampling,
        }


@dataclass(frozen=True)
class BuildResult:
    state: str
    destination: str
    source_bytes: int
    destination_bytes: int
    saved_bytes: int
    converted: int
    kept: int
    skipped: int
    errors: int
    elapsed_seconds: float
    health_passed: bool
    hardlinked: int
    copied: int
    repaired_missing_references: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class OptimizationError(RuntimeError):
    pass


def _safe_destination(source_root: Path, destination: Path) -> tuple[Path, Path]:
    source = source_root.resolve()
    target = destination.resolve()
    if target == source or source in target.parents:
        raise OptimizationError("destination must be outside the source data root")
    if target in source.parents:
        raise OptimizationError("source data root must not be inside destination")
    return source, target


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        for attempt in range(6):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.01 * (2**attempt))
    finally:
        temporary.unlink(missing_ok=True)


def _status(destination: Path, state: str, **extra: object) -> None:
    _write_json(
        destination / STATUS_FILE,
        {
            "schema_version": 1,
            "state": state,
            **extra,
        },
    )


def load_analysis_manifest(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise OptimizationError(f"invalid analyzer manifest at line {line_number}") from exc
            if not isinstance(record, dict) or "relative_path" not in record:
                raise OptimizationError(f"invalid analyzer record at line {line_number}")
            records.append(record)
    return records


def _target_paths(records: Sequence[dict[str, object]]) -> dict[str, str]:
    occupied = {str(record["relative_path"]).casefold() for record in records}
    mapping: dict[str, str] = {}
    for record in records:
        source_relative = str(record["relative_path"])
        if record.get("classification") != "jpeg_candidate":
            mapping[source_relative.casefold()] = source_relative
            continue
        path = Path(source_relative)
        if path.suffix.casefold() in {".jpg", ".jpeg", ".jpe", ".jfif"}:
            target_relative = source_relative
        else:
            candidate = path.with_suffix(".jpg").as_posix()
            if candidate.casefold() in occupied and candidate.casefold() != source_relative.casefold():
                suffix = hashlib.sha256(source_relative.encode("utf-8")).hexdigest()[:10]
                candidate = path.with_name(f"{path.stem}.optimized-{suffix}.jpg").as_posix()
            target_relative = candidate
        occupied.add(target_relative.casefold())
        mapping[source_relative.casefold()] = target_relative
    return mapping


def _copy_database(source_database: Path, destination_database: Path) -> None:
    destination_database.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_database, destination_database)
    destination_database.chmod(destination_database.stat().st_mode | stat.S_IWRITE | stat.S_IWUSR)


def _hardlink_or_copy(source: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
        return "hardlinked"
    except OSError:
        shutil.copy2(source, destination)
        return "copied"


def _convert_png(source: Path, destination: Path, policy: ConversionPolicy) -> tuple[int, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    try:
        with Image.open(source) as image:
            image.load()
            original_size = image.size
            rgb = image.convert("RGB")
            rgb.save(temporary, format="JPEG", **policy.jpeg_options())
        with Image.open(temporary) as check:
            check.load()
            if check.format != "JPEG" or check.size != original_size:
                raise OptimizationError("converted JPEG failed format or resolution validation")
        checksum = sha256_file(temporary)
        size = temporary.stat().st_size
        os.replace(temporary, destination)
        return size, checksum
    finally:
        temporary.unlink(missing_ok=True)


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in connection.execute(f"pragma table_info({quoted_identifier(table)})")}


def _reference_rows(connection: sqlite3.Connection) -> Iterable[tuple[str, str, int, object]]:
    tables = {
        row["name"] for row in connection.execute("select name from sqlite_master where type = 'table'").fetchall()
    }
    for table, desired_columns in REFERENCE_COLUMNS.items():
        if table not in tables:
            continue
        columns = _table_columns(connection, table)
        for column in desired_columns:
            if column not in columns:
                continue
            query = (
                f"select rowid as source_rowid, {quoted_identifier(column)} as media_path "
                f"from {quoted_identifier(table)} where {quoted_identifier(column)} is not null"
            )
            for row in connection.execute(query):
                yield table, column, int(row["source_rowid"]), row["media_path"]


def _update_copied_references(
    destination_database: Path,
    target_mapping: dict[str, str],
    present_source_paths: set[str],
) -> tuple[int, int]:
    updates = 0
    repaired_missing = 0
    connection = sqlite3.connect(destination_database)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("begin immediate")
        for table, column, rowid, raw_value in list(_reference_rows(connection)):
            normalized, state = normalize_reference(raw_value)
            if normalized is None or state != "managed":
                continue
            normalized_key = normalized.casefold()
            if normalized_key in target_mapping:
                target = target_mapping[normalized_key]
            elif normalized_key not in present_source_paths:
                target = "default/nofoto.jpg"
                repaired_missing += 1
            else:
                target = normalized
            if raw_value != target:
                connection.execute(
                    f"update {quoted_identifier(table)} set {quoted_identifier(column)} = ? where rowid = ?",
                    (target, rowid),
                )
                updates += 1
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return updates, repaired_missing


def _table_counts(database: Path) -> dict[str, int]:
    connection = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        tables = [
            row["name"]
            for row in connection.execute(
                "select name from sqlite_master where type = 'table' and name not like 'sqlite_%' order by name"
            )
        ]
        return {table: int(connection.execute(f"select count(*) from {quoted_identifier(table)}").fetchone()[0]) for table in tables}
    finally:
        connection.close()


def _referenced_paths(database: Path) -> tuple[Counter[str], int]:
    connection = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    references: Counter[str] = Counter()
    external = 0
    try:
        for _, _, _, raw_value in _reference_rows(connection):
            normalized, state = normalize_reference(raw_value)
            if normalized is None:
                if isinstance(raw_value, str) and raw_value.strip():
                    external += 1
                continue
            references[normalized.casefold()] += 1
    finally:
        connection.close()
    return references, external


def health_check_optimized_copy(
    source_root: Path,
    source_database: Path,
    destination: Path,
    destination_database: Path,
    conversion_records: Sequence[dict[str, object]],
) -> dict[str, object]:
    connection = sqlite3.connect(destination_database)
    try:
        integrity = str(connection.execute("pragma integrity_check").fetchone()[0])
        foreign_keys = connection.execute("pragma foreign_key_check").fetchall()
    finally:
        connection.close()

    source_counts = _table_counts(source_database)
    destination_counts = _table_counts(destination_database)
    references, external = _referenced_paths(destination_database)
    destination_files = inventory_files(destination)
    destination_paths = {entry.relative_path.casefold(): entry for entry in destination_files}
    missing: list[str] = []
    decode_errors: list[str] = []
    for relative_key in sorted(references):
        entry = destination_paths.get(relative_key)
        if entry is None:
            missing.append(relative_key)
            continue
        try:
            with Image.open(entry.path) as image:
                image.load()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            decode_errors.append(relative_key)

    source_unreferenced = sum(1 for record in conversion_records if not int(record.get("reference_count", 0)))
    destination_unreferenced = sum(1 for entry in destination_files if entry.relative_path.casefold() not in references)
    source_root_text = str(source_root.resolve()).casefold()
    back_references = 0
    connection = sqlite3.connect(f"file:{destination_database.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        for _, _, _, raw_value in _reference_rows(connection):
            if isinstance(raw_value, str) and source_root_text in raw_value.casefold():
                back_references += 1
    finally:
        connection.close()

    passed = all(
        (
            integrity == "ok",
            not foreign_keys,
            source_counts == destination_counts,
            not missing,
            not decode_errors,
            external == 0,
            back_references == 0,
            destination_unreferenced <= source_unreferenced,
        )
    )
    return {
        "passed": passed,
        "integrity_check": integrity,
        "foreign_key_violations": len(foreign_keys),
        "entity_counts_parity": source_counts == destination_counts,
        "source_table_counts": source_counts,
        "destination_table_counts": destination_counts,
        "referenced_unique_paths": len(references),
        "missing_referenced_paths": len(missing),
        "decode_errors": len(decode_errors),
        "external_references": external,
        "source_back_references": back_references,
        "source_unreferenced_files": source_unreferenced,
        "destination_unreferenced_files": destination_unreferenced,
        "new_orphans_produced": max(0, destination_unreferenced - source_unreferenced),
    }


def build_optimized_copy(
    source_root: Path,
    source_database: Path,
    analysis_manifest: Path,
    destination: Path,
    policy: ConversionPolicy | None = None,
    *,
    restart_incomplete: bool = False,
    interrupt_after: int | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> BuildResult:
    policy = policy or ConversionPolicy()
    source, target = _safe_destination(source_root, destination)
    records = load_analysis_manifest(analysis_manifest)
    status_path = target / STATUS_FILE
    if status_path.exists():
        existing = json.loads(status_path.read_text(encoding="utf-8"))
        if existing.get("state") == "complete" and existing.get("policy") == asdict(policy):
            return BuildResult(**existing["result"])
        if not restart_incomplete:
            raise OptimizationError("destination contains an incomplete or incompatible optimization run")
        shutil.rmtree(target)
    elif target.exists() and any(target.iterdir()):
        if not restart_incomplete:
            raise OptimizationError("destination is not empty")
        shutil.rmtree(target)

    target.mkdir(parents=True, exist_ok=True)
    (target / INCOMPLETE_MARKER).write_text("incomplete\n", encoding="ascii")
    started = time.perf_counter()
    source_db_before = sha256_file(source_database)
    source_files_before = inventory_files(source)
    source_media_before = metadata_fingerprint(source_files_before)
    source_total_bytes = sum(entry.size for entry in source_files_before)
    source_by_path = {entry.relative_path.casefold(): entry for entry in source_files_before}
    manifest_paths = {str(record["relative_path"]).casefold() for record in records}
    if set(source_by_path) != manifest_paths:
        raise OptimizationError("analysis manifest does not match current source inventory")

    target_mapping = _target_paths(records)
    destination_database = target / "database" / "MyDatabase.sqlite"
    _copy_database(source_database, destination_database)
    _status(
        target,
        "running",
        policy=asdict(policy),
        processed=0,
        total=len(records),
        source_database_sha256=source_db_before,
        source_media_fingerprint=source_media_before,
    )

    converted = kept = skipped = errors = hardlinked = copied = 0
    destination_total_bytes = 0
    conversion_records: list[dict[str, object]] = []
    manifest_output = target / CONVERSION_MANIFEST
    try:
        with manifest_output.open("w", encoding="utf-8", newline="\n") as output:
            for index, record in enumerate(records, start=1):
                source_relative = str(record["relative_path"])
                source_entry = source_by_path[source_relative.casefold()]
                target_relative = target_mapping[source_relative.casefold()]
                destination_path = target / Path(target_relative)
                result_record: dict[str, object] = {
                    "old_path": source_relative,
                    "new_path": target_relative,
                    "source_format": record.get("actual_format"),
                    "target_format": (
                        "JPEG" if record.get("classification") == "jpeg_candidate" else record.get("actual_format")
                    ),
                    "source_width": record.get("width"),
                    "source_height": record.get("height"),
                    "target_width": record.get("width"),
                    "target_height": record.get("height"),
                    "source_bytes": source_entry.size,
                    "source_sha256": record.get("source_sha256"),
                    "status": "",
                    "reason": "",
                    "target_bytes": 0,
                    "target_sha256": "",
                    "saved_bytes": 0,
                }
                if record.get("classification") == "jpeg_candidate":
                    target_bytes, target_sha = _convert_png(source_entry.path, destination_path, policy)
                    converted += 1
                    result_record.update(
                        status="converted",
                        reason=policy.version,
                        target_bytes=target_bytes,
                        target_sha256=target_sha,
                        saved_bytes=source_entry.size - target_bytes,
                    )
                else:
                    transfer = _hardlink_or_copy(source_entry.path, destination_path)
                    hardlinked += transfer == "hardlinked"
                    copied += transfer == "copied"
                    kept += 1
                    result_record.update(
                        status="kept",
                        reason=str(record.get("classification_reason", record.get("classification", "policy"))),
                        target_bytes=source_entry.size,
                        target_sha256=record.get("source_sha256", ""),
                        saved_bytes=0,
                    )
                destination_total_bytes += int(result_record["target_bytes"])
                conversion_records.append(result_record)
                output.write(json.dumps(result_record, ensure_ascii=False, sort_keys=True) + "\n")
                output.flush()
                if progress:
                    progress(index, len(records))
                if index % 250 == 0:
                    _status(
                        target,
                        "running",
                        policy=asdict(policy),
                        processed=index,
                        total=len(records),
                        converted=converted,
                        kept=kept,
                        errors=errors,
                    )
                if interrupt_after is not None and index >= interrupt_after:
                    raise InterruptedError("injected optimization interruption")

        _, repaired_missing = _update_copied_references(
            destination_database,
            target_mapping,
            set(source_by_path),
        )
        health = health_check_optimized_copy(
            source,
            source_database,
            target,
            destination_database,
            records,
        )
        _write_json(target / HEALTH_REPORT, health)
        if not health["passed"]:
            raise OptimizationError("optimized copy health check failed")

        source_db_after = sha256_file(source_database)
        source_files_after = inventory_files(source)
        source_media_after = metadata_fingerprint(source_files_after)
        if source_db_after != source_db_before or source_media_after != source_media_before:
            raise OptimizationError("source DB/media changed during optimized-copy build")

        result = BuildResult(
            state="complete",
            destination=str(target),
            source_bytes=source_total_bytes,
            destination_bytes=destination_total_bytes,
            saved_bytes=source_total_bytes - destination_total_bytes,
            converted=converted,
            kept=kept,
            skipped=skipped,
            errors=errors,
            elapsed_seconds=time.perf_counter() - started,
            health_passed=True,
            hardlinked=hardlinked,
            copied=copied,
            repaired_missing_references=repaired_missing,
        )
        (target / INCOMPLETE_MARKER).unlink(missing_ok=True)
        (target / COMPLETE_MARKER).write_text("complete\n", encoding="ascii")
        _status(target, "complete", policy=asdict(policy), result=result.as_dict(), health=health)
        return result
    except BaseException as exc:
        _status(
            target,
            "incomplete",
            policy=asdict(policy),
            processed=len(conversion_records),
            total=len(records),
            converted=converted,
            kept=kept,
            errors=errors + 1,
            error_type=type(exc).__name__,
        )
        raise
