from __future__ import annotations

from contextlib import closing
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
from typing import Callable, Literal
from uuid import uuid4

from ..config import Settings
from ..db import open_write_connection
from .audit import log_action
from .media_lifecycle import (
    MANAGED_IMAGE_EXTENSIONS,
    MediaLifecycleError,
    MediaReferenceExclusion,
    managed_image_reference_count_in_connection,
    managed_image_reference_counts_in_connection,
    normalize_managed_image_path,
)
from .write_guard import ensure_dangerous_action_allowed


QUARANTINE_DIR_NAME = ".deletion-quarantine"
MANIFEST_VERSION = 1
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SAFE_OPERATION_ID = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


class DeletionLifecycleError(RuntimeError):
    pass


class DeletionValidationError(DeletionLifecycleError):
    pass


class DeletionBlockedError(DeletionLifecycleError):
    pass


class DeletionStateMismatchError(DeletionLifecycleError):
    pass


class DeletionRecoveryRequired(DeletionLifecycleError):
    pass


class DeletionCrash(RuntimeError):
    """Fault-injection signal that intentionally leaves a recoverable manifest."""


@dataclass(frozen=True)
class RowCountExpectation:
    table: str
    column: str
    value: int
    before: int
    after: int = 0


@dataclass(frozen=True)
class OwnedPath:
    role: Literal["person_directory", "reward_directory", "mark_directory", "guide_image"]
    relative_path: str
    kind: Literal["directory", "file"]


@dataclass(frozen=True)
class DeletePlan:
    operation_id: str
    entity_type: str
    entity_ids: tuple[int, ...]
    expected_row_counts: tuple[RowCountExpectation, ...]
    normalized_references: tuple[str, ...]
    excluded_rows: tuple[MediaReferenceExclusion, ...]
    owned_paths: tuple[OwnedPath, ...]


@dataclass(frozen=True)
class DeletionExecutionResult:
    operation_id: str
    status: Literal["completed", "already_completed", "cleanup_pending", "restored"]
    staged_paths: int = 0
    preserved_shared_references: int = 0
    error: str | None = None

    @property
    def warning_required(self) -> bool:
        return self.status == "cleanup_pending"


DatabasePhase = Callable[[object], None]
FaultHook = Callable[[str], None]


def person_owned_directory(person_id: int) -> OwnedPath:
    safe_id = _positive_id(person_id, "person_id")
    return OwnedPath("person_directory", f"Source/{safe_id}", "directory")


def reward_owned_directory(person_id: int, reward_id: int) -> OwnedPath:
    safe_person_id = _positive_id(person_id, "person_id")
    safe_reward_id = _positive_id(reward_id, "reward_id")
    return OwnedPath("reward_directory", f"Source/{safe_person_id}/{safe_reward_id}", "directory")


def mark_owned_directory(mark_id: int) -> OwnedPath:
    safe_id = _positive_id(mark_id, "mark_id")
    return OwnedPath("mark_directory", f"SourceMark/{safe_id}", "directory")


def guide_owned_image(settings: Settings, raw_path: object) -> OwnedPath:
    try:
        normalized = normalize_managed_image_path(settings, raw_path, allowed_roots=frozenset({"GuideImages"}))
    except MediaLifecycleError as exc:
        raise DeletionValidationError("Guide image path is outside the managed GuideImages root.") from exc
    if len(Path(normalized).parts) != 2:
        raise DeletionValidationError("Guide image path must be a flat GuideImages file.")
    return OwnedPath("guide_image", normalized, "file")


def build_delete_plan(
    settings: Settings,
    *,
    entity_type: str,
    entity_ids: tuple[int, ...],
    expected_row_counts: tuple[RowCountExpectation, ...],
    reference_paths: tuple[object, ...] = (),
    excluded_rows: tuple[MediaReferenceExclusion, ...] = (),
    owned_paths: tuple[OwnedPath, ...] = (),
    operation_id: str | None = None,
) -> DeletePlan:
    try:
        normalized_references = tuple(
            sorted(
                {
                    normalize_managed_image_path(settings, path)
                    for path in reference_paths
                    if path not in {None, ""}
                }
            )
        )
    except MediaLifecycleError as exc:
        raise DeletionValidationError("Delete plan contains an unsafe managed media reference.") from exc
    plan = DeletePlan(
        operation_id=operation_id or uuid4().hex,
        entity_type=str(entity_type or "").strip(),
        entity_ids=tuple(int(entity_id) for entity_id in entity_ids),
        expected_row_counts=expected_row_counts,
        normalized_references=normalized_references,
        excluded_rows=excluded_rows,
        owned_paths=owned_paths,
    )
    _validate_plan(plan)
    return plan


def execute_delete_plan(
    settings: Settings,
    plan: DeletePlan,
    database_phase: DatabasePhase,
    *,
    fault_hook: FaultHook | None = None,
) -> DeletionExecutionResult:
    ensure_dangerous_action_allowed(settings)
    _validate_plan(plan)
    existing = _existing_operation_result(settings, plan, fault_hook=fault_hook)
    if existing is not None:
        return existing

    manifest: dict[str, object] | None = None
    committed = False
    connection = open_write_connection(settings.rewards_db_path, settings.write_mode)
    try:
        connection.execute("begin immediate")
        _verify_row_counts(connection, plan.expected_row_counts, state="before")
        manifest = _prepare_manifest(settings, plan)
        _call_fault(fault_hook, "manifest_prepared")
        manifest = _stage_owned_paths(settings, connection, plan, manifest)
        _call_fault(fault_hook, "paths_staged")
        database_phase(connection)
        _verify_row_counts(connection, plan.expected_row_counts, state="after")
        _call_fault(fault_hook, "database_phase_complete")
        connection.commit()
        committed = True
        _call_fault(fault_hook, "database_committed")
    except DeletionCrash:
        if not committed:
            connection.rollback()
        raise
    except Exception:
        if committed:
            error = "Database commit succeeded, but deletion finalization was interrupted."
            _log_operation(plan, "cleanup_pending", manifest, error)
            return DeletionExecutionResult(
                plan.operation_id,
                "cleanup_pending",
                _staged_count(manifest),
                _preserved_count(manifest),
                error,
            )
        connection.rollback()
        if manifest is not None:
            try:
                _restore_staged_paths(settings, manifest)
                _remove_operation_directory(settings, plan.operation_id)
            except Exception as restore_error:
                _log_operation(plan, "recovery_required", manifest, str(restore_error))
                raise DeletionRecoveryRequired(
                    "Deletion rolled back, but staged paths require manifest-scoped recovery."
                ) from restore_error
        _log_operation(plan, "rolled_back", manifest)
        raise
    finally:
        connection.close()

    assert manifest is not None
    try:
        manifest = _write_manifest_state(settings, manifest, "committed")
        _call_fault(fault_hook, "manifest_committed")
        _write_receipt(settings, plan, "purging")
        _call_fault(fault_hook, "before_purge")
        _purge_operation(settings, plan.operation_id)
        _write_receipt(settings, plan, "completed")
    except DeletionCrash:
        raise
    except Exception as exc:
        _log_operation(plan, "cleanup_pending", manifest, str(exc))
        return DeletionExecutionResult(
            plan.operation_id,
            "cleanup_pending",
            _staged_count(manifest),
            _preserved_count(manifest),
            str(exc),
        )

    result = DeletionExecutionResult(
        plan.operation_id,
        "completed",
        _staged_count(manifest),
        _preserved_count(manifest),
    )
    _log_operation(plan, "completed", manifest)
    return result


def recover_delete_operation(
    settings: Settings,
    operation_id: str,
    *,
    fault_hook: FaultHook | None = None,
) -> DeletionExecutionResult:
    ensure_dangerous_action_allowed(settings)
    _validate_operation_id(operation_id)
    receipt = _read_receipt(settings, operation_id)
    if receipt is not None and receipt.get("status") == "completed":
        return DeletionExecutionResult(operation_id, "already_completed")

    manifest = _read_manifest(settings, operation_id)
    if manifest is None and receipt is None:
        raise DeletionValidationError("Deletion operation manifest was not found.")
    plan = _plan_from_mapping((manifest or receipt or {}).get("plan"))
    if plan.operation_id != operation_id:
        raise DeletionValidationError("Deletion operation identity does not match its manifest.")

    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        connection.execute("begin immediate")
        state = _row_count_state(connection, plan.expected_row_counts)
        connection.commit()

    if state == "before":
        if receipt is not None and receipt.get("status") == "purging":
            raise DeletionStateMismatchError("A purging receipt cannot be reconciled with pre-delete database rows.")
        if manifest is not None:
            _restore_staged_paths(settings, manifest)
            _remove_operation_directory(settings, operation_id)
        _log_operation(plan, "restored", manifest)
        return DeletionExecutionResult(
            operation_id,
            "restored",
            _staged_count(manifest),
            _preserved_count(manifest),
        )
    if state != "after":
        raise DeletionStateMismatchError("Database rows do not match either side of the deletion plan.")

    try:
        if receipt is None:
            _write_receipt(settings, plan, "purging")
        _call_fault(fault_hook, "before_purge")
        if manifest is not None:
            _purge_operation(settings, operation_id)
        _write_receipt(settings, plan, "completed")
    except Exception as exc:
        _log_operation(plan, "cleanup_pending", manifest, str(exc))
        return DeletionExecutionResult(
            operation_id,
            "cleanup_pending",
            _staged_count(manifest),
            _preserved_count(manifest),
            str(exc),
        )
    _log_operation(plan, "completed_after_recovery", manifest)
    return DeletionExecutionResult(
        operation_id,
        "completed",
        _staged_count(manifest),
        _preserved_count(manifest),
    )


def recorded_delete_plan(settings: Settings, operation_id: str) -> DeletePlan | None:
    """Return the immutable plan recorded for one operation without changing state."""
    _validate_operation_id(operation_id)
    receipt = _read_receipt(settings, operation_id)
    manifest = _read_manifest(settings, operation_id)
    if receipt is not None and manifest is not None:
        receipt_plan = _plan_from_mapping(receipt.get("plan"))
        manifest_plan = _plan_from_mapping(manifest.get("plan"))
        if _plan_digest(receipt_plan) != _plan_digest(manifest_plan):
            raise DeletionStateMismatchError("Deletion receipt and manifest contain different plans.")
    recorded = manifest or receipt
    if recorded is None:
        return None
    return _plan_from_mapping(recorded.get("plan"))


def _existing_operation_result(
    settings: Settings,
    plan: DeletePlan,
    *,
    fault_hook: FaultHook | None,
) -> DeletionExecutionResult | None:
    receipt = _read_receipt(settings, plan.operation_id)
    manifest = _read_manifest(settings, plan.operation_id)
    if receipt is None and manifest is None:
        return None
    recorded_plan = _plan_from_mapping((receipt or manifest or {}).get("plan"))
    if _plan_digest(recorded_plan) != _plan_digest(plan):
        raise DeletionStateMismatchError("Operation ID is already associated with a different deletion plan.")
    recovered = recover_delete_operation(settings, plan.operation_id, fault_hook=fault_hook)
    if recovered.status == "restored":
        return None
    if recovered.status == "completed":
        return replace(recovered, status="already_completed")
    return recovered


def _prepare_manifest(settings: Settings, plan: DeletePlan) -> dict[str, object]:
    operation_dir = _operation_dir(settings, plan.operation_id, create=True)
    manifest_path = operation_dir / "manifest.json"
    if manifest_path.exists():
        raise DeletionStateMismatchError("Deletion operation manifest already exists.")
    manifest: dict[str, object] = {
        "version": MANIFEST_VERSION,
        "state": "prepared",
        "created_at": _now(),
        "updated_at": _now(),
        "plan": _plan_mapping(plan),
        "entries": [],
        "preserved_shared_references": [],
    }
    _write_json_atomic(manifest_path, manifest)
    return manifest


def _stage_owned_paths(
    settings: Settings,
    connection,
    plan: DeletePlan,
    manifest: dict[str, object],
) -> dict[str, object]:
    preserved: set[str] = set()
    covered_references: set[str] = set()
    managed_paths_by_owned: dict[str, set[str]] = {}
    for owned in plan.owned_paths:
        source = _owned_target(settings, owned)
        if source.exists() or source.is_symlink():
            managed_paths_by_owned[owned.relative_path] = _validate_source_tree(settings, owned, source)
            _validate_same_volume(settings, source)
        else:
            managed_paths_by_owned[owned.relative_path] = set()
        for reference in plan.normalized_references:
            if _owned_path_covers(owned, reference):
                covered_references.add(reference)

    paths_to_check = set(plan.normalized_references)
    for paths in managed_paths_by_owned.values():
        paths_to_check.update(paths)
    reference_counts = managed_image_reference_counts_in_connection(
        connection,
        settings,
        paths_to_check,
        excluded_rows=plan.excluded_rows,
    )

    for owned in plan.owned_paths:
        managed_paths = managed_paths_by_owned[owned.relative_path]
        if owned.kind == "file":
            if reference_counts.get(owned.relative_path, 0):
                preserved.add(owned.relative_path)
            continue
        if any(reference_counts.get(path, 0) for path in managed_paths):
            raise DeletionBlockedError("An external database reference points inside an owned directory.")

    for reference in plan.normalized_references:
        if reference in covered_references:
            continue
        count = reference_counts.get(reference, 0)
        if count:
            preserved.add(reference)
            continue
        raise DeletionBlockedError("A planned media reference is outside the entity's exact owned paths.")

    manifest = dict(manifest)
    manifest["preserved_shared_references"] = sorted(preserved)
    _write_manifest(settings, plan.operation_id, manifest)
    entries: list[dict[str, object]] = []
    for owned in plan.owned_paths:
        source = _owned_target(settings, owned)
        if owned.kind == "file" and owned.relative_path in preserved:
            entries.append(_entry_mapping(owned, exists=source.exists(), status="shared"))
            continue
        if not source.exists() and not source.is_symlink():
            entries.append(_entry_mapping(owned, exists=False, status="missing"))
            continue
        destination = _operation_dir(settings, plan.operation_id, create=False) / "payload" / owned.relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        entry = _entry_mapping(owned, exists=True, status="moving")
        entry["destination"] = destination.relative_to(settings.rewards_data_dir.resolve()).as_posix()
        entries.append(entry)
        manifest["entries"] = entries
        _write_manifest(settings, plan.operation_id, manifest)
        os.replace(source, destination)
        entry["status"] = "staged"
        manifest["entries"] = entries
        _write_manifest(settings, plan.operation_id, manifest)
    manifest["state"] = "staged"
    manifest["entries"] = entries
    return _write_manifest(settings, plan.operation_id, manifest)


def _validate_source_tree(
    settings: Settings,
    owned: OwnedPath,
    source: Path,
) -> set[str]:
    _validate_no_symlink_chain(settings, source)
    if owned.kind == "file":
        if not source.is_file():
            raise DeletionBlockedError("Owned image path is not a regular file.")
        _validate_regular_file(source)
        try:
            return {normalize_managed_image_path(settings, owned.relative_path)}
        except MediaLifecycleError as exc:
            raise DeletionBlockedError("Owned image path does not satisfy the managed media policy.") from exc

    if not source.is_dir():
        raise DeletionBlockedError("Owned directory path is not a directory.")
    managed_paths: set[str] = set()
    for entry in sorted(source.rglob("*"), key=lambda item: item.as_posix()):
        if entry.is_symlink():
            raise DeletionBlockedError("Symbolic links are not allowed in an owned deletion tree.")
        if entry.is_dir():
            continue
        if not entry.is_file():
            raise DeletionBlockedError("Special filesystem entries are not allowed in an owned deletion tree.")
        _validate_regular_file(entry)
        relative = entry.relative_to(settings.rewards_data_dir.resolve()).as_posix()
        if entry.suffix.lower() not in MANAGED_IMAGE_EXTENSIONS:
            continue
        try:
            normalized = normalize_managed_image_path(settings, relative)
        except MediaLifecycleError as exc:
            raise DeletionBlockedError("Owned image path does not satisfy the managed media policy.") from exc
        managed_paths.add(normalized)
    return managed_paths


def _validate_regular_file(path: Path) -> None:
    stat_result = path.stat(follow_symlinks=False)
    if stat_result.st_nlink != 1:
        raise DeletionBlockedError("Hard-linked files have ambiguous ownership and cannot be staged.")


def _validate_same_volume(settings: Settings, source: Path) -> None:
    quarantine = _quarantine_root(settings, create=True)
    probe = source
    while not probe.exists() and probe != settings.rewards_data_dir:
        probe = probe.parent
    if probe.stat().st_dev != quarantine.stat().st_dev:
        raise DeletionBlockedError("Owned paths and deletion quarantine must be on the same filesystem.")


def _verify_row_counts(connection, expectations: tuple[RowCountExpectation, ...], *, state: str) -> None:
    for expectation in expectations:
        expected = expectation.before if state == "before" else expectation.after
        actual = _row_count(connection, expectation)
        if actual != expected:
            raise DeletionStateMismatchError(
                f"Delete plan row count mismatch for {expectation.table}: expected {expected}, found {actual}."
            )


def _row_count_state(connection, expectations: tuple[RowCountExpectation, ...]) -> str:
    before = all(_row_count(connection, item) == item.before for item in expectations)
    after = all(_row_count(connection, item) == item.after for item in expectations)
    if before and not after:
        return "before"
    if after and not before:
        return "after"
    if before and after:
        return "after"
    return "mixed"


def _row_count(connection, expectation: RowCountExpectation) -> int:
    _validate_identifier(expectation.table)
    _validate_identifier(expectation.column)
    row = connection.execute(
        f'SELECT count(*) AS count FROM "{expectation.table}" WHERE "{expectation.column}" = ?',
        (expectation.value,),
    ).fetchone()
    return int(row["count"])


def _restore_staged_paths(settings: Settings, manifest: dict[str, object]) -> None:
    entries = list(manifest.get("entries") or [])
    for raw_entry in reversed(entries):
        entry = dict(raw_entry)
        if entry.get("status") not in {"moving", "staged"}:
            continue
        owned = _owned_path_from_mapping(entry)
        source = _owned_target(settings, owned)
        destination = _manifest_destination(settings, entry)
        source_exists = source.exists() or source.is_symlink()
        destination_exists = destination.exists() or destination.is_symlink()
        if source_exists and destination_exists:
            raise DeletionRecoveryRequired("Both original and quarantined paths exist.")
        if destination_exists:
            source.parent.mkdir(parents=True, exist_ok=True)
            os.replace(destination, source)
        elif not source_exists:
            raise DeletionRecoveryRequired("Neither original nor quarantined path exists.")


def _purge_operation(settings: Settings, operation_id: str) -> None:
    operation_dir = _operation_dir(settings, operation_id, create=False)
    if operation_dir.exists():
        shutil.rmtree(operation_dir)


def _remove_operation_directory(settings: Settings, operation_id: str) -> None:
    operation_dir = _operation_dir(settings, operation_id, create=False)
    if operation_dir.exists():
        shutil.rmtree(operation_dir)


def _write_manifest_state(
    settings: Settings,
    manifest: dict[str, object],
    state: str,
) -> dict[str, object]:
    updated = dict(manifest)
    updated["state"] = state
    plan = _plan_from_mapping(updated.get("plan"))
    return _write_manifest(settings, plan.operation_id, updated)


def _write_manifest(
    settings: Settings,
    operation_id: str,
    manifest: dict[str, object],
) -> dict[str, object]:
    updated = dict(manifest)
    updated["updated_at"] = _now()
    path = _operation_dir(settings, operation_id, create=True) / "manifest.json"
    _write_json_atomic(path, updated)
    return updated


def _read_manifest(settings: Settings, operation_id: str) -> dict[str, object] | None:
    path = _operation_dir(settings, operation_id, create=False) / "manifest.json"
    if not path.is_file():
        return None
    return _read_json(path)


def _write_receipt(settings: Settings, plan: DeletePlan, status: str) -> None:
    path = _receipt_path(settings, plan.operation_id, create=True)
    receipt = {
        "version": MANIFEST_VERSION,
        "status": status,
        "updated_at": _now(),
        "plan_digest": _plan_digest(plan),
        "plan": _plan_mapping(plan),
    }
    _write_json_atomic(path, receipt)


def _read_receipt(settings: Settings, operation_id: str) -> dict[str, object] | None:
    path = _receipt_path(settings, operation_id, create=False)
    if not path.is_file():
        return None
    return _read_json(path)


def _receipt_path(settings: Settings, operation_id: str, *, create: bool) -> Path:
    _validate_operation_id(operation_id)
    receipts = _quarantine_root(settings, create=create) / "receipts"
    if create:
        receipts.mkdir(parents=True, exist_ok=True)
    return receipts / f"{operation_id}.json"


def _operation_dir(settings: Settings, operation_id: str, *, create: bool) -> Path:
    _validate_operation_id(operation_id)
    operation_dir = _quarantine_root(settings, create=create) / "operations" / operation_id
    if create:
        operation_dir.mkdir(parents=True, exist_ok=True)
    return operation_dir


def _quarantine_root(settings: Settings, *, create: bool) -> Path:
    data_root = settings.rewards_data_dir
    if data_root.is_symlink():
        raise DeletionValidationError("Data root symlinks are not supported for deletion quarantine.")
    resolved_root = data_root.resolve()
    quarantine = resolved_root / QUARANTINE_DIR_NAME
    if quarantine.is_symlink():
        raise DeletionValidationError("Deletion quarantine must not be a symbolic link.")
    if create:
        quarantine.mkdir(parents=True, exist_ok=True)
    return quarantine


def _owned_target(settings: Settings, owned: OwnedPath) -> Path:
    _validate_owned_path(owned)
    data_root = settings.rewards_data_dir.resolve()
    target = data_root / Path(owned.relative_path)
    if target == data_root:
        raise DeletionValidationError("Data root cannot be an owned deletion path.")
    try:
        target.relative_to(data_root)
    except ValueError as exc:
        raise DeletionValidationError("Owned path escapes the data root.") from exc
    return target


def _manifest_destination(settings: Settings, entry: dict[str, object]) -> Path:
    raw = str(entry.get("destination") or "")
    candidate = Path(raw)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise DeletionValidationError("Invalid quarantine destination in manifest.")
    destination = settings.rewards_data_dir.resolve() / candidate
    operation_id = _plan_from_mapping(_read_manifest_plan_from_entry(settings, entry)).operation_id
    operation_dir = _operation_dir(settings, operation_id, create=False)
    try:
        destination.relative_to(operation_dir)
    except ValueError as exc:
        raise DeletionValidationError("Manifest destination escapes its operation quarantine.") from exc
    return destination


def _read_manifest_plan_from_entry(settings: Settings, entry: dict[str, object]) -> object:
    destination = str(entry.get("destination") or "")
    parts = Path(destination).parts
    try:
        index = parts.index("operations")
        operation_id = parts[index + 1]
    except (ValueError, IndexError) as exc:
        raise DeletionValidationError("Invalid quarantine destination in manifest.") from exc
    manifest = _read_manifest(settings, operation_id)
    if manifest is None:
        raise DeletionValidationError("Deletion manifest is missing during recovery.")
    return manifest.get("plan")


def _validate_no_symlink_chain(settings: Settings, target: Path) -> None:
    data_root = settings.rewards_data_dir.resolve()
    relative = target.relative_to(data_root)
    current = data_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise DeletionBlockedError("Symbolic links are not allowed in an owned deletion path.")


def _owned_path_covers(owned: OwnedPath, normalized_reference: str) -> bool:
    owned_path = Path(owned.relative_path)
    reference = Path(normalized_reference)
    if owned.kind == "file":
        return reference == owned_path
    try:
        reference.relative_to(owned_path)
        return True
    except ValueError:
        return False


def _entry_mapping(owned: OwnedPath, *, exists: bool, status: str) -> dict[str, object]:
    return {
        "role": owned.role,
        "relative_path": owned.relative_path,
        "kind": owned.kind,
        "existed": exists,
        "status": status,
    }


def _owned_path_from_mapping(value: object) -> OwnedPath:
    if not isinstance(value, dict):
        raise DeletionValidationError("Invalid owned path manifest entry.")
    owned = OwnedPath(
        role=str(value.get("role") or ""),  # type: ignore[arg-type]
        relative_path=str(value.get("relative_path") or ""),
        kind=str(value.get("kind") or ""),  # type: ignore[arg-type]
    )
    _validate_owned_path(owned)
    return owned


def _plan_mapping(plan: DeletePlan) -> dict[str, object]:
    return {
        "operation_id": plan.operation_id,
        "entity_type": plan.entity_type,
        "entity_ids": list(plan.entity_ids),
        "expected_row_counts": [asdict(item) for item in plan.expected_row_counts],
        "normalized_references": list(plan.normalized_references),
        "excluded_rows": [asdict(item) for item in plan.excluded_rows],
        "owned_paths": [asdict(item) for item in plan.owned_paths],
    }


def _plan_from_mapping(value: object) -> DeletePlan:
    if not isinstance(value, dict):
        raise DeletionValidationError("Invalid deletion plan manifest.")
    try:
        plan = DeletePlan(
            operation_id=str(value["operation_id"]),
            entity_type=str(value["entity_type"]),
            entity_ids=tuple(int(item) for item in value.get("entity_ids", [])),
            expected_row_counts=tuple(
                RowCountExpectation(
                    table=str(item["table"]),
                    column=str(item["column"]),
                    value=int(item["value"]),
                    before=int(item["before"]),
                    after=int(item.get("after", 0)),
                )
                for item in value.get("expected_row_counts", [])
            ),
            normalized_references=tuple(str(item) for item in value.get("normalized_references", [])),
            excluded_rows=tuple(
                MediaReferenceExclusion(str(item["table"]), int(item["row_id"]))
                for item in value.get("excluded_rows", [])
            ),
            owned_paths=tuple(_owned_path_from_mapping(item) for item in value.get("owned_paths", [])),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise DeletionValidationError("Invalid deletion plan manifest.") from exc
    _validate_plan(plan)
    return plan


def _validate_plan(plan: DeletePlan) -> None:
    _validate_operation_id(plan.operation_id)
    if not plan.entity_type or not _SAFE_IDENTIFIER.fullmatch(plan.entity_type):
        raise DeletionValidationError("Invalid deletion entity type.")
    if not plan.entity_ids or any(entity_id <= 0 for entity_id in plan.entity_ids):
        raise DeletionValidationError("Deletion plan requires positive entity IDs.")
    if not plan.expected_row_counts:
        raise DeletionValidationError("Deletion plan requires row-count expectations.")
    for expectation in plan.expected_row_counts:
        _validate_identifier(expectation.table)
        _validate_identifier(expectation.column)
        if expectation.before < 0 or expectation.after < 0:
            raise DeletionValidationError("Row-count expectations cannot be negative.")
    for exclusion in plan.excluded_rows:
        _validate_identifier(exclusion.table)
        if exclusion.row_id <= 0:
            raise DeletionValidationError("Reference exclusions require positive row IDs.")
    for owned in plan.owned_paths:
        _validate_owned_path(owned)
    paths = [Path(item.relative_path) for item in plan.owned_paths]
    if len(set(paths)) != len(paths):
        raise DeletionValidationError("Owned deletion paths must be unique.")
    for index, left in enumerate(paths):
        for right in paths[index + 1 :]:
            if _path_contains(left, right) or _path_contains(right, left):
                raise DeletionValidationError("Owned deletion paths must not overlap.")


def _validate_owned_path(owned: OwnedPath) -> None:
    path = Path(owned.relative_path)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise DeletionValidationError("Invalid owned deletion path.")
    parts = path.parts
    if owned.role == "person_directory":
        valid = owned.kind == "directory" and len(parts) == 2 and parts[0] == "Source" and _positive_part(parts[1])
    elif owned.role == "reward_directory":
        valid = (
            owned.kind == "directory"
            and len(parts) == 3
            and parts[0] == "Source"
            and _positive_part(parts[1])
            and _positive_part(parts[2])
        )
    elif owned.role == "mark_directory":
        valid = owned.kind == "directory" and len(parts) == 2 and parts[0] == "SourceMark" and _positive_part(parts[1])
    elif owned.role == "guide_image":
        valid = (
            owned.kind == "file"
            and len(parts) == 2
            and parts[0] == "GuideImages"
            and path.suffix.lower() in MANAGED_IMAGE_EXTENSIONS
        )
    else:
        valid = False
    if not valid:
        raise DeletionValidationError("Owned path does not match its exact managed ownership role.")


def _validate_identifier(value: str) -> None:
    if not _SAFE_IDENTIFIER.fullmatch(value):
        raise DeletionValidationError("Unsafe SQLite identifier in deletion plan.")


def _validate_operation_id(operation_id: str) -> None:
    if not _SAFE_OPERATION_ID.fullmatch(operation_id):
        raise DeletionValidationError("Invalid deletion operation ID.")


def _positive_id(value: int, label: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise DeletionValidationError(f"Invalid {label}.") from exc
    if parsed <= 0:
        raise DeletionValidationError(f"Invalid {label}.")
    return parsed


def _positive_part(value: str) -> bool:
    return value.isdigit() and int(value) > 0 and str(int(value)) == value


def _path_contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
        return child != parent
    except ValueError:
        return False


def _plan_digest(plan: DeletePlan) -> str:
    payload = json.dumps(_plan_mapping(plan), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _write_json_atomic(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeletionRecoveryRequired("Deletion operation metadata is unreadable.") from exc
    if not isinstance(value, dict):
        raise DeletionRecoveryRequired("Deletion operation metadata is invalid.")
    return value


def _call_fault(fault_hook: FaultHook | None, checkpoint: str) -> None:
    if fault_hook is not None:
        fault_hook(checkpoint)


def _staged_count(manifest: dict[str, object] | None) -> int:
    if manifest is None:
        return 0
    return sum(1 for item in manifest.get("entries", []) if item.get("status") in {"moving", "staged"})


def _preserved_count(manifest: dict[str, object] | None) -> int:
    if manifest is None:
        return 0
    return len(manifest.get("preserved_shared_references", []))


def _log_operation(
    plan: DeletePlan,
    status: str,
    manifest: dict[str, object] | None,
    error: str | None = None,
) -> None:
    log_action(
        "deletion_operation",
        plan.entity_type,
        plan.entity_ids[0] if len(plan.entity_ids) == 1 else None,
        {
            "operation_id": plan.operation_id,
            "status": status,
            "entity_ids": list(plan.entity_ids),
            "staged_paths": _staged_count(manifest),
            "preserved_shared_references": _preserved_count(manifest),
            "error": error,
        },
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
