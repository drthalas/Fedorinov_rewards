from __future__ import annotations

import json
import os
import sqlite3
import time
from collections import defaultdict
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence
from uuid import uuid4

from .managed_media_analysis import (
    FileEntry,
    inspect_file,
    inventory_files,
    load_references,
    metadata_fingerprint,
)

from .media_image_policy import JPEG_POLICY_VERSION
from .media_optimization import load_analysis_manifest


INDEX_SCHEMA_VERSION = 1


class OptimizationIndexError(RuntimeError):
    pass


@dataclass(frozen=True)
class IndexRunResult:
    state: str
    run_id: str
    indexed: int
    unchanged: int
    new: int
    changed: int
    policy_invalidated: int
    missing: int
    renamed: int
    decoded: int
    elapsed_seconds: float
    inventory_fingerprint: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


INDEX_SCHEMA = """
create table metadata (
    key text primary key,
    value text not null
);
create table media_objects (
    identity text primary key,
    relative_path text not null,
    size integer not null,
    mtime_ns integer not null,
    sha256 text not null,
    actual_format text,
    width integer,
    height integer,
    has_alpha_channel integer not null default 0,
    has_transparency integer not null default 0,
    policy_version text not null,
    decision text not null,
    status text not null,
    converted_target text,
    saved_bytes integer not null default 0,
    renamed_from text,
    last_processed_at text not null,
    run_id text not null
);
create index media_objects_sha256 on media_objects(sha256);
create index media_objects_status on media_objects(status);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _metadata_set(connection: sqlite3.Connection, key: str, value: object) -> None:
    connection.execute(
        "insert into metadata(key, value) values (?, ?) "
        "on conflict(key) do update set value = excluded.value",
        (key, json.dumps(value, ensure_ascii=False, sort_keys=True)),
    )


def _metadata_get(connection: sqlite3.Connection, key: str) -> object | None:
    row = connection.execute("select value from metadata where key = ?", (key,)).fetchone()
    return json.loads(row[0]) if row is not None else None


def _load_conversion_records(path: Path | None) -> dict[str, dict[str, object]]:
    if path is None:
        return {}
    records: dict[str, dict[str, object]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            records[str(record["old_path"]).casefold()] = record
    return records


def _manifest_record_values(
    record: dict[str, object],
    conversion: dict[str, object] | None,
    policy_version: str,
    run_id: str,
    processed_at: str,
) -> tuple[object, ...]:
    relative_path = str(record["relative_path"])
    return (
        relative_path.casefold(),
        relative_path,
        int(record["source_bytes"]),
        int(record["source_mtime_ns"]),
        str(record["source_sha256"]),
        record.get("actual_format"),
        record.get("width"),
        record.get("height"),
        bool(record.get("has_alpha_channel")),
        bool(record.get("has_transparency")),
        policy_version,
        str(record.get("classification") or "unknown"),
        "indexed",
        conversion.get("new_path") if conversion else None,
        int(conversion.get("saved_bytes") or 0) if conversion else 0,
        None,
        processed_at,
        run_id,
    )


def _destination_records(
    source_records: Sequence[dict[str, object]],
    conversions: dict[str, dict[str, object]],
    destination_files: dict[str, FileEntry],
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for source in source_records:
        conversion = conversions.get(str(source["relative_path"]).casefold())
        if conversion is None:
            raise OptimizationIndexError("conversion manifest is incomplete")
        relative_path = str(conversion["new_path"])
        entry = destination_files.get(relative_path.casefold())
        if entry is None:
            raise OptimizationIndexError("converted target is missing from destination inventory")
        target_format = conversion.get("target_format")
        if not target_format:
            target_format = "JPEG" if conversion.get("status") == "converted" else source.get("actual_format")
        record = dict(source)
        record.update(
            relative_path=relative_path,
            source_bytes=entry.size,
            source_mtime_ns=entry.mtime_ns,
            source_sha256=conversion.get("target_sha256") or source.get("source_sha256"),
            actual_format=target_format,
            width=conversion.get("target_width") or source.get("width"),
            height=conversion.get("target_height") or source.get("height"),
            classification=(
                "already_optimized" if conversion.get("status") == "converted" else source.get("classification")
            ),
            classification_reason=(conversion.get("reason") or source.get("classification_reason")),
        )
        records.append(record)
    return records


def build_index_from_manifest(
    data_root: Path,
    analysis_manifest: Path,
    index_path: Path,
    *,
    conversion_manifest: Path | None = None,
    policy_version: str = JPEG_POLICY_VERSION,
) -> IndexRunResult:
    started = time.perf_counter()
    source_records = load_analysis_manifest(analysis_manifest)
    files = inventory_files(data_root)
    conversions = _load_conversion_records(conversion_manifest)
    conversions_by_target = {
        str(record["new_path"]).casefold(): record for record in conversions.values()
    }
    file_by_path = {item.relative_path.casefold(): item for item in files}
    file_paths = set(file_by_path)
    source_record_paths = {str(item["relative_path"]).casefold() for item in source_records}
    if file_paths == source_record_paths:
        records = source_records
    elif conversions:
        records = _destination_records(source_records, conversions, file_by_path)
    else:
        raise OptimizationIndexError("analysis manifest does not match current media inventory")
    record_paths = {str(item["relative_path"]).casefold() for item in records}
    if file_paths != record_paths:
        raise OptimizationIndexError("converted manifest does not match destination media inventory")

    run_id = uuid4().hex
    processed_at = _utc_now()
    index_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = index_path.with_name(index_path.name + ".tmp")
    temporary.unlink(missing_ok=True)
    with closing(sqlite3.connect(temporary)) as connection:
        connection.executescript(INDEX_SCHEMA)
        connection.executemany(
            """
            insert into media_objects(
                identity, relative_path, size, mtime_ns, sha256, actual_format,
                width, height, has_alpha_channel, has_transparency, policy_version,
                decision, status, converted_target, saved_bytes, renamed_from,
                last_processed_at, run_id
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _manifest_record_values(
                    record,
                    conversions.get(str(record["relative_path"]).casefold())
                    or conversions_by_target.get(str(record["relative_path"]).casefold()),
                    policy_version,
                    run_id,
                    processed_at,
                )
                for record in records
            ),
        )
        _metadata_set(connection, "schema_version", INDEX_SCHEMA_VERSION)
        _metadata_set(connection, "policy_version", policy_version)
        _metadata_set(connection, "data_root", str(data_root.resolve()))
        _metadata_set(connection, "inventory_fingerprint", metadata_fingerprint(files))
        _metadata_set(connection, "last_run_state", "complete")
        _metadata_set(connection, "last_run_id", run_id)
        _metadata_set(connection, "last_run_at", processed_at)
        connection.commit()
    os.replace(temporary, index_path)
    return IndexRunResult(
        state="complete",
        run_id=run_id,
        indexed=len(records),
        unchanged=0,
        new=len(records),
        changed=0,
        policy_invalidated=0,
        missing=0,
        renamed=0,
        decoded=0,
        elapsed_seconds=time.perf_counter() - started,
        inventory_fingerprint=metadata_fingerprint(files),
    )


def _row_dicts(connection: sqlite3.Connection) -> dict[str, dict[str, object]]:
    connection.row_factory = sqlite3.Row
    return {
        str(row["identity"]): dict(row)
        for row in connection.execute("select * from media_objects")
    }


def _upsert_inspection(
    connection: sqlite3.Connection,
    entry: FileEntry,
    inspection: dict[str, object],
    policy_version: str,
    run_id: str,
    processed_at: str,
    renamed_from: str | None,
) -> None:
    identity = entry.relative_path.casefold()
    connection.execute(
        """
        insert into media_objects(
            identity, relative_path, size, mtime_ns, sha256, actual_format,
            width, height, has_alpha_channel, has_transparency, policy_version,
            decision, status, converted_target, saved_bytes, renamed_from,
            last_processed_at, run_id
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(identity) do update set
            relative_path=excluded.relative_path,
            size=excluded.size,
            mtime_ns=excluded.mtime_ns,
            sha256=excluded.sha256,
            actual_format=excluded.actual_format,
            width=excluded.width,
            height=excluded.height,
            has_alpha_channel=excluded.has_alpha_channel,
            has_transparency=excluded.has_transparency,
            policy_version=excluded.policy_version,
            decision=excluded.decision,
            status=excluded.status,
            converted_target=excluded.converted_target,
            saved_bytes=excluded.saved_bytes,
            renamed_from=excluded.renamed_from,
            last_processed_at=excluded.last_processed_at,
            run_id=excluded.run_id
        """,
        (
            identity,
            entry.relative_path,
            entry.size,
            entry.mtime_ns,
            str(inspection["source_sha256"]),
            inspection.get("actual_format"),
            inspection.get("width"),
            inspection.get("height"),
            bool(inspection.get("has_alpha_channel")),
            bool(inspection.get("has_transparency")),
            policy_version,
            str(inspection.get("classification") or "unknown"),
            "indexed",
            None,
            0,
            renamed_from,
            processed_at,
            run_id,
        ),
    )


def run_incremental_index(
    data_root: Path,
    index_path: Path,
    *,
    database: Path | None = None,
    policy_version: str = JPEG_POLICY_VERSION,
    interrupt_after: int | None = None,
    decoded_hook: Callable[[Path], None] | None = None,
) -> IndexRunResult:
    started = time.perf_counter()
    if not index_path.is_file():
        raise OptimizationIndexError("optimization index does not exist")
    files = inventory_files(data_root)
    current = {item.relative_path.casefold(): item for item in files}
    references = load_references(database)[0] if database is not None else {}
    run_id = uuid4().hex
    processed_at = _utc_now()

    with closing(sqlite3.connect(index_path)) as connection:
        previous = _row_dicts(connection)
        schema_version = _metadata_get(connection, "schema_version")
        if schema_version != INDEX_SCHEMA_VERSION:
            raise OptimizationIndexError("unsupported optimization index schema")
        indexed_root = Path(str(_metadata_get(connection, "data_root") or "")).resolve()
        if indexed_root != data_root.resolve():
            raise OptimizationIndexError("optimization index belongs to a different data root")
        missing_ids = sorted(set(previous) - set(current))
        new_ids: list[str] = []
        changed_ids: list[str] = []
        invalidated_ids: list[str] = []
        unchanged = 0
        for identity, entry in current.items():
            old = previous.get(identity)
            if old is None:
                new_ids.append(identity)
            elif int(old["size"]) != entry.size or int(old["mtime_ns"]) != entry.mtime_ns:
                changed_ids.append(identity)
            elif str(old["policy_version"]) != policy_version:
                invalidated_ids.append(identity)
            else:
                unchanged += 1

        pending = sorted(new_ids) + sorted(changed_ids) + sorted(invalidated_ids)
        missing_by_sha: dict[str, list[str]] = defaultdict(list)
        for identity in missing_ids:
            checksum = str(previous[identity].get("sha256") or "")
            if checksum:
                missing_by_sha[checksum].append(identity)
        for identities in missing_by_sha.values():
            identities.sort()

        _metadata_set(connection, "last_run_state", "running")
        _metadata_set(connection, "last_run_id", run_id)
        connection.commit()
        decoded = renamed = 0
        try:
            for identity in pending:
                entry = current[identity]
                inspection = inspect_file(entry, int(references.get(identity, 0)))
                decoded += 1
                if decoded_hook is not None:
                    decoded_hook(entry.path)
                renamed_from = None
                checksum = str(inspection.get("source_sha256") or "")
                candidates = missing_by_sha.get(checksum, [])
                if candidates and identity in new_ids:
                    renamed_from = candidates.pop(0)
                    renamed += 1
                _upsert_inspection(
                    connection,
                    entry,
                    inspection,
                    policy_version,
                    run_id,
                    processed_at,
                    renamed_from,
                )
                connection.commit()
                if interrupt_after is not None and decoded >= interrupt_after:
                    raise InterruptedError("injected incremental index interruption")

            for identity in missing_ids:
                connection.execute(
                    "update media_objects set status = ?, run_id = ?, last_processed_at = ? where identity = ?",
                    ("missing", run_id, processed_at, identity),
                )
            fingerprint = metadata_fingerprint(files)
            _metadata_set(connection, "policy_version", policy_version)
            _metadata_set(connection, "inventory_fingerprint", fingerprint)
            _metadata_set(connection, "last_run_state", "complete")
            _metadata_set(connection, "last_run_id", run_id)
            _metadata_set(connection, "last_run_at", processed_at)
            connection.commit()
        except BaseException:
            _metadata_set(connection, "last_run_state", "interrupted")
            _metadata_set(connection, "last_run_id", run_id)
            connection.commit()
            raise

        indexed = int(connection.execute("select count(*) from media_objects").fetchone()[0])

    return IndexRunResult(
        state="complete",
        run_id=run_id,
        indexed=indexed,
        unchanged=unchanged,
        new=len(new_ids),
        changed=len(changed_ids),
        policy_invalidated=len(invalidated_ids),
        missing=len(missing_ids),
        renamed=renamed,
        decoded=decoded,
        elapsed_seconds=time.perf_counter() - started,
        inventory_fingerprint=fingerprint,
    )
