#!/usr/bin/env python3
"""Manage a private full-data fixture without exposing its file structure."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import sys
import time
import zipfile
from contextlib import closing
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


DB_RELATIVE_PATH = Path("database") / "MyDatabase.sqlite"
MEDIA_ROOTS = ("Source", "SourceMark", "default", "GuideImages")
IMAGE_EXTENSIONS = {
    ".bmp",
    ".gif",
    ".jfif",
    ".jp2",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}
IGNORED_METADATA_NAMES = {".ds_store"}


class FixtureError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_files(root: Path) -> Iterable[Path]:
    return sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file() and path.name.lower() not in IGNORED_METADATA_NAMES
        ),
        key=lambda path: path.relative_to(root).as_posix().encode("utf-8"),
    )


def tree_content_fingerprint(root: Path) -> tuple[str, int, int]:
    digest = hashlib.sha256()
    file_count = 0
    byte_count = 0
    for path in iter_files(root):
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        digest.update(hashlib.sha256(relative.encode("utf-8")).digest())
        digest.update(size.to_bytes(8, "big"))
        digest.update(bytes.fromhex(sha256_file(path)))
        file_count += 1
        byte_count += size
    return digest.hexdigest(), file_count, byte_count


def sqlite_health(db_path: Path) -> dict[str, Any]:
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        integrity = connection.execute("pragma integrity_check").fetchone()[0]
        foreign_key_violations = len(connection.execute("pragma foreign_key_check").fetchall())
        table_names = {
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type = 'table'"
            ).fetchall()
        }
        counts = {}
        for table in ("person", "rewards", "mark", "guide"):
            if table in table_names:
                counts[table] = connection.execute(
                    f'select count(*) from "{table}"'
                ).fetchone()[0]
    return {
        "integrity_check": integrity,
        "foreign_key_violations": foreign_key_violations,
        "row_counts": counts,
    }


def sampled_image_health(root: Path, sample_size: int) -> dict[str, Any]:
    try:
        from PIL import Image
    except ImportError:
        return {
            "sample_requested": sample_size,
            "sampled": 0,
            "decoded": 0,
            "failed": 0,
            "status": "Pillow unavailable",
        }

    candidates = []
    for directory in MEDIA_ROOTS:
        media_root = root / directory
        if not media_root.is_dir():
            continue
        candidates.extend(
            path
            for path in media_root.rglob("*")
            if path.is_file()
            and path.name.lower() not in IGNORED_METADATA_NAMES
            and path.suffix.lower() in IMAGE_EXTENSIONS
        )
    candidates.sort(
        key=lambda path: hashlib.sha256(
            path.relative_to(root).as_posix().encode("utf-8")
        ).digest()
    )
    sample = candidates[:sample_size]
    decoded = 0
    failures: dict[str, int] = {}
    formats: dict[str, int] = {}
    for path in sample:
        try:
            with Image.open(path) as image:
                image.verify()
                image_format = image.format or "UNKNOWN"
            formats[image_format] = formats.get(image_format, 0) + 1
            decoded += 1
        except Exception as error:  # diagnostic classification only
            name = type(error).__name__
            failures[name] = failures.get(name, 0) + 1
    return {
        "sample_requested": sample_size,
        "sampled": len(sample),
        "decoded": decoded,
        "failed": len(sample) - decoded,
        "formats": dict(sorted(formats.items())),
        "failure_types": dict(sorted(failures.items())),
    }


def inventory(
    root: Path,
    *,
    include_tree_fingerprint: bool,
    sample_size: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = root.resolve()
    db_path = root / DB_RELATIVE_PATH
    if not root.is_dir():
        raise FixtureError("Fixture root does not exist or is not a directory.")
    if not db_path.is_file():
        raise FixtureError("Expected SQLite database is absent.")

    media_files = 0
    media_bytes = 0
    image_files = 0
    for directory in MEDIA_ROOTS:
        media_root = root / directory
        if not media_root.is_dir():
            continue
        for path in media_root.rglob("*"):
            if not path.is_file() or path.name.lower() in IGNORED_METADATA_NAMES:
                continue
            media_files += 1
            media_bytes += path.stat().st_size
            if path.suffix.lower() in IMAGE_EXTENSIONS:
                image_files += 1

    tree_fingerprint = None
    tree_files = None
    tree_bytes = None
    if include_tree_fingerprint:
        tree_fingerprint, tree_files, tree_bytes = tree_content_fingerprint(root)

    health = sqlite_health(db_path)
    summary = {
        "profile": "sergey-full",
        "database": {
            "bytes": db_path.stat().st_size,
            "sha256": sha256_file(db_path),
            **health,
        },
        "media": {
            "files": media_files,
            "bytes": media_bytes,
            "image_extension_files": image_files,
            "sample": sampled_image_health(root, sample_size),
        },
        "tree": {
            "files": tree_files,
            "bytes": tree_bytes,
            "content_fingerprint": tree_fingerprint,
        },
    }
    private = {
        "schema": 1,
        "profile": "sergey-full",
        "root": str(root),
        "database_path": str(db_path),
        "created_at_epoch": int(time.time()),
        "summary": summary,
    }
    return summary, private


def write_private_manifest(path: Path, payload: dict[str, Any]) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if os.name != "nt":
        temporary.chmod(stat.S_IRUSR | stat.S_IWUSR)
    temporary.replace(path)


def load_private_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if payload.get("schema") != 1 or payload.get("profile") != "sergey-full":
        raise FixtureError("Unsupported private manifest.")
    return payload


def ensure_outside(child: Path, parent: Path, label: str) -> None:
    child = child.resolve()
    parent = parent.resolve()
    if child == parent or parent in child.parents:
        raise FixtureError(f"{label} must be outside the read-only master.")


def set_database_copy_mode(path: Path, *, writable: bool) -> None:
    if hasattr(os, "chflags") and hasattr(path.stat(), "st_flags"):
        removable_flags = 0
        for name in ("UF_APPEND", "UF_IMMUTABLE", "SF_APPEND", "SF_IMMUTABLE"):
            removable_flags |= getattr(stat, name, 0)
        os.chflags(path, path.stat().st_flags & ~removable_flags)
    current = stat.S_IMODE(path.stat().st_mode)
    if writable:
        path.chmod(current | stat.S_IRUSR | stat.S_IWUSR)
    else:
        path.chmod((current | stat.S_IRUSR) & ~(
            stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
        ))


def prepare_run(
    master_root: Path,
    state_root: Path,
    run_id: str,
    *,
    apply: bool,
) -> dict[str, Any]:
    master_root = master_root.resolve()
    state_root = state_root.resolve()
    ensure_outside(state_root, master_root, "State root")
    source_db = master_root / DB_RELATIVE_PATH
    if not source_db.is_file():
        raise FixtureError("Expected master SQLite database is absent.")
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    if not run_id or any(char not in allowed for char in run_id):
        raise FixtureError("Run ID must use only ASCII letters, digits, '-' and '_'.")

    baseline_db = state_root / "baseline" / "MyDatabase.sqlite"
    run_db = state_root / "runs" / run_id / "database" / "MyDatabase.sqlite"
    source_sha = sha256_file(source_db)
    result = {
        "profile": "sergey-full",
        "apply": apply,
        "copy_scope": "database-only",
        "master_database_sha256": source_sha,
        "baseline_exists": baseline_db.is_file(),
        "run_exists": run_db.is_file(),
    }
    if not apply:
        return result

    baseline_db.parent.mkdir(parents=True, exist_ok=True)
    if not baseline_db.exists():
        shutil.copy2(source_db, baseline_db)
    set_database_copy_mode(baseline_db, writable=False)
    if sha256_file(baseline_db) != source_sha:
        raise FixtureError("Baseline database does not match the master database.")

    run_db.parent.mkdir(parents=True, exist_ok=True)
    if run_db.exists():
        set_database_copy_mode(run_db, writable=True)
    shutil.copy2(baseline_db, run_db)
    set_database_copy_mode(run_db, writable=True)
    health = sqlite_health(run_db)
    if health["integrity_check"] != "ok" or health["foreign_key_violations"]:
        raise FixtureError("Prepared run database failed SQLite health checks.")
    result.update(
        {
            "baseline_exists": True,
            "run_exists": True,
            "run_database_sha256": sha256_file(run_db),
            "integrity_check": health["integrity_check"],
            "foreign_key_violations": health["foreign_key_violations"],
            "runtime_environment": {
                "REWARDS_DATA_DIR": str(master_root),
                "REWARDS_DB_PATH": str(run_db),
                "READ_ONLY": "false",
                "WRITE_MODE": "true",
                "UPDATE_CHECK_ENABLED": "false",
            },
        }
    )
    return result


def verify_manifest(manifest_path: Path, *, full: bool) -> dict[str, Any]:
    manifest = load_private_manifest(manifest_path)
    root = Path(manifest["root"])
    expected = manifest["summary"]
    current, _private = inventory(
        root,
        include_tree_fingerprint=full,
        sample_size=32,
    )
    checks = {
        "database_sha256": (
            current["database"]["sha256"] == expected["database"]["sha256"]
        ),
        "database_integrity": current["database"]["integrity_check"] == "ok",
        "foreign_keys": current["database"]["foreign_key_violations"] == 0,
        "media_file_count": current["media"]["files"] == expected["media"]["files"],
        "media_bytes": current["media"]["bytes"] == expected["media"]["bytes"],
    }
    if full:
        checks["tree_content_fingerprint"] = (
            current["tree"]["content_fingerprint"]
            == expected["tree"]["content_fingerprint"]
        )
    return {
        "profile": "sergey-full",
        "mode": "full" if full else "quick",
        "checks": checks,
        "pass": all(checks.values()),
    }


def safe_extract_archive(
    archive: Path,
    destination: Path,
    *,
    expected_sha256: str,
    apply: bool,
    strip_single_root: bool = False,
) -> dict[str, Any]:
    archive = archive.resolve()
    destination = destination.resolve()
    if not archive.is_file():
        raise FixtureError("Archive does not exist.")
    archive_sha256 = sha256_file(archive)
    if archive_sha256.lower() != expected_sha256.lower():
        raise FixtureError("Archive SHA256 does not match the expected value.")
    if destination.exists() and any(destination.iterdir()):
        raise FixtureError("Destination must not exist or must be empty.")

    with zipfile.ZipFile(archive) as bundle:
        entry_parts: dict[str, tuple[str, ...]] = {}
        for entry in bundle.infolist():
            pure = PurePosixPath(entry.filename.replace("\\", "/"))
            parts = pure.parts
            if pure.is_absolute() or ".." in parts or (parts and ":" in parts[0]):
                raise FixtureError("Archive contains an unsafe path.")
            entry_parts[entry.filename] = parts
        entries = [entry for entry in bundle.infolist() if not entry.is_dir()]
        uncompressed_bytes = sum(entry.file_size for entry in entries)
        common_root = None
        if strip_single_root:
            roots = {
                entry_parts[entry.filename][0]
                for entry in bundle.infolist()
                if entry_parts[entry.filename]
            }
            if len(roots) != 1:
                raise FixtureError("Archive does not have exactly one top-level root.")
            common_root = roots.pop()
        for entry in bundle.infolist():
            parts = entry_parts[entry.filename]
            if strip_single_root:
                if not parts or parts[0] != common_root:
                    raise FixtureError("Archive top-level root is inconsistent.")
                parts = parts[1:]
            target = (destination / Path(*parts)).resolve()
            try:
                target.relative_to(destination)
            except ValueError as error:
                raise FixtureError("Archive contains an unsafe path.") from error
        free_bytes = shutil.disk_usage(destination.parent).free
        required_bytes = int(uncompressed_bytes * 1.10)
        result = {
            "profile": "sergey-full",
            "apply": apply,
            "archive_sha256": archive_sha256,
            "archive_entries": len(entries),
            "uncompressed_bytes": uncompressed_bytes,
            "free_bytes": free_bytes,
            "required_bytes": required_bytes,
            "space_ok": free_bytes >= required_bytes,
            "strip_single_root": strip_single_root,
        }
        if not result["space_ok"]:
            raise FixtureError("Insufficient free space for safe extraction.")
        if not apply:
            return result
        destination.mkdir(parents=True, exist_ok=True)
        if not strip_single_root:
            bundle.extractall(destination)
        else:
            for entry in bundle.infolist():
                parts = entry_parts[entry.filename][1:]
                if not parts:
                    continue
                target = destination / Path(*parts)
                if entry.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(entry) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, 4 * 1024 * 1024)
    result["extracted"] = True
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    inventory_parser = commands.add_parser("inventory")
    inventory_parser.add_argument("--root", type=Path, required=True)
    inventory_parser.add_argument("--private-manifest", type=Path)
    inventory_parser.add_argument("--full-fingerprint", action="store_true")
    inventory_parser.add_argument("--sample-size", type=int, default=32)

    prepare_parser = commands.add_parser("prepare-run")
    prepare_parser.add_argument("--master-root", type=Path, required=True)
    prepare_parser.add_argument("--state-root", type=Path, required=True)
    prepare_parser.add_argument("--run-id", required=True)
    prepare_parser.add_argument("--apply", action="store_true")

    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--private-manifest", type=Path, required=True)
    verify_parser.add_argument("--full", action="store_true")

    extract_parser = commands.add_parser("extract")
    extract_parser.add_argument("--archive", type=Path, required=True)
    extract_parser.add_argument("--destination", type=Path, required=True)
    extract_parser.add_argument("--expected-sha256", required=True)
    extract_parser.add_argument("--strip-single-root", action="store_true")
    extract_parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "inventory":
            summary, private = inventory(
                args.root,
                include_tree_fingerprint=args.full_fingerprint,
                sample_size=args.sample_size,
            )
            if args.private_manifest:
                write_private_manifest(args.private_manifest, private)
            result = summary
        elif args.command == "prepare-run":
            result = prepare_run(
                args.master_root,
                args.state_root,
                args.run_id,
                apply=args.apply,
            )
        elif args.command == "verify":
            result = verify_manifest(args.private_manifest, full=args.full)
        else:
            result = safe_extract_archive(
                args.archive,
                args.destination,
                expected_sha256=args.expected_sha256,
                apply=args.apply,
                strip_single_root=args.strip_single_root,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (FixtureError, OSError, sqlite3.Error, zipfile.BadZipFile) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
