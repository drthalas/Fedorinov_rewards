from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import sqlite3
import threading
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..config import Settings
from .managed_media_analysis import (
    MISSING_REFERENCE_PLACEHOLDER,
    inventory_files,
    normalize_reference,
    quoted_identifier,
    run_analysis,
)
from .media_image_policy import JPEG_POLICY_VERSION
from .media_optimization import (
    COMPLETE_MARKER,
    CONVERSION_MANIFEST,
    HEALTH_REPORT,
    INCOMPLETE_MARKER,
    STATUS_FILE,
    OptimizationError,
    OptimizationTargetNotWritableError,
    ConversionPolicy,
    _convert_png,
    _reference_rows,
    build_optimized_copy,
)
from .media_optimization_index import build_index_from_manifest, run_incremental_index


OPERATION_STATUS = "operation-status.json"
ACTIVE_WORKSPACE = "active-workspace.json"
LAST_CHECK = "last-check.json"
ANALYSIS_DIR = "baseline"
SOURCE_INDEX = "source-index.sqlite"
OPTIMIZED_INDEX = "optimized-index.sqlite"
SPACE_RESERVE_PERCENT = 10
SPACE_GUARD_INTERVAL = 64
SPACE_SERVICE_OVERHEAD_BYTES = 128 * 1024 * 1024

PHASE_LABELS = {
    "inventory": "Проверка изображений",
    "baseline": "Проверка изображений",
    "preparation": "Подготовка",
    "creating_copy": "Создание оптимизированной копии",
    "optimizing_images": "Оптимизация изображений",
    "checking_health": "Проверка базы и изображений",
    "preparing_workspace": "Подготовка новой рабочей базы",
    "complete": "Готово",
    "stopped_safely": "Безопасная остановка",
    "error": "Операция остановлена",
}

INITIAL_OPERATION_PHASES = {
    "check": "inventory",
    "optimize": "preparation",
    "incremental_optimize": "optimizing_images",
}


class MediaOptimizationWorkflowError(RuntimeError):
    pass


class MediaOptimizationInsufficientSpaceError(MediaOptimizationWorkflowError):
    def __init__(self, required: int, available: int) -> None:
        self.required = required
        self.available = available
        missing = max(0, required - available)
        super().__init__(
            "Недостаточно свободного места для безопасной оптимизации. "
            f"Требуется не менее {required / 1_000_000_000:.1f} ГБ, "
            f"доступно {available / 1_000_000_000:.1f} ГБ. "
            f"Освободите ещё минимум {missing / 1_000_000_000:.1f} ГБ и повторите проверку."
        )


class MediaOptimizationMissingReferenceError(MediaOptimizationWorkflowError):
    pass


@dataclass
class _ActiveOperation:
    thread: threading.Thread
    cancel: threading.Event


_operations: dict[str, _ActiveOperation] = {}
_operations_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_root(settings: Settings) -> Path:
    return (settings.configured_rewards_data_dir or settings.rewards_data_dir).resolve()


def _state_dir(settings: Settings) -> Path:
    return settings.media_optimization_state_dir.resolve()


def _target_root(settings: Settings) -> Path:
    return settings.media_optimization_target_dir.resolve()


def _analysis_dir(settings: Settings) -> Path:
    return _state_dir(settings) / ANALYSIS_DIR


def _analysis_manifest(settings: Settings) -> Path:
    return _analysis_dir(settings) / "media_manifest.jsonl"


def _analysis_summary(settings: Settings) -> Path:
    return _analysis_dir(settings) / "summary.json"


def _index_path(settings: Settings, data_root: Path) -> Path:
    return _state_dir(settings) / (OPTIMIZED_INDEX if data_root.resolve() == _target_root(settings) else SOURCE_INDEX)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
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


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _operation_key(settings: Settings) -> str:
    return str(_state_dir(settings)).casefold()


def _write_operation(settings: Settings, **payload: object) -> None:
    _write_json(
        _state_dir(settings) / OPERATION_STATUS,
        {"updated_at": _now(), **payload},
    )


def _operation_running(settings: Settings) -> bool:
    key = _operation_key(settings)
    with _operations_lock:
        operation = _operations.get(key)
        if operation is not None and not operation.thread.is_alive():
            _operations.pop(key, None)
            operation = None
    return operation is not None


def _progress_writer(settings: Settings, operation: str, phase: str) -> Callable[[int, int], None]:
    last_written = -1

    def write(processed: int, total: int) -> None:
        nonlocal last_written
        percent = int(processed * 100 / total) if total else 0
        if processed != total and percent == last_written:
            return
        last_written = percent
        key = _operation_key(settings)
        with _operations_lock:
            active = _operations.get(key)
            cancelled = bool(active and active.cancel.is_set())
        if cancelled:
            raise InterruptedError("media optimization cancelled")
        _write_operation(
            settings,
            state="running",
            operation=operation,
            phase=phase,
            phase_label=PHASE_LABELS.get(phase, phase),
            processed=processed,
            total=total,
            percent=percent,
        )

    return write


def _stage_writer(settings: Settings, operation: str) -> Callable[[str], None]:
    def write(phase: str) -> None:
        _write_operation(
            settings,
            state="running",
            operation=operation,
            phase=phase,
            phase_label=PHASE_LABELS.get(phase, phase),
            processed=0,
            total=0,
            percent=0,
        )

    return write


def _is_cancelled(settings: Settings) -> bool:
    key = _operation_key(settings)
    with _operations_lock:
        active = _operations.get(key)
        return bool(active and active.cancel.is_set())


def run_check(settings: Settings) -> dict[str, object]:
    data_root = settings.rewards_data_dir.resolve()
    database = settings.rewards_db_path.resolve()
    index_path = _index_path(settings, data_root)
    _write_operation(settings, state="running", operation="check", phase="inventory", percent=0)
    if index_path.is_file():
        result = run_incremental_index(data_root, index_path, database=database)
        mode = "delta"
    elif data_root == _source_root(settings):
        summary = run_analysis(
            data_root,
            database,
            _analysis_dir(settings),
            progress=_progress_writer(settings, "check", "baseline"),
            cancelled=lambda: _is_cancelled(settings),
        )
        result = build_index_from_manifest(
            data_root,
            _analysis_manifest(settings),
            index_path,
        )
        mode = "baseline"
        _write_json(_analysis_summary(settings), summary)
    else:
        conversion_manifest = _target_root(settings) / CONVERSION_MANIFEST
        if not _analysis_manifest(settings).is_file() or not conversion_manifest.is_file():
            raise MediaOptimizationWorkflowError("Нет данных для восстановления индекса оптимизированной копии")
        result = build_index_from_manifest(
            data_root,
            _analysis_manifest(settings),
            index_path,
            conversion_manifest=conversion_manifest,
        )
        mode = "optimized_baseline"
    payload = {"mode": mode, **result.as_dict(), "completed_at": _now()}
    _write_json(_state_dir(settings) / LAST_CHECK, payload)
    _write_operation(settings, state="complete", operation="check", phase="complete", percent=100, result=payload)
    return payload


def run_optimize(settings: Settings, *, restart_incomplete: bool = False) -> dict[str, object]:
    source_root = _source_root(settings)
    source_database = settings.rewards_db_path.resolve()
    target_root = _target_root(settings)
    if not _analysis_manifest(settings).is_file():
        raise MediaOptimizationWorkflowError("Сначала выполните проверку исходных изображений")
    if not source_database.is_file():
        raise MediaOptimizationWorkflowError("Рабочая база данных не найдена")
    budget = _optimization_space_budget(settings)
    _require_optimization_space(budget)
    _require_reference_repair_ready(settings)
    _write_operation(
        settings,
        state="running",
        operation="optimize",
        phase="preparation",
        phase_label=PHASE_LABELS["preparation"],
        percent=0,
    )
    result = build_optimized_copy(
        source_root,
        source_database,
        _analysis_manifest(settings),
        target_root,
        restart_incomplete=restart_incomplete,
        progress=_progress_writer(settings, "optimize", "optimizing_images"),
        stage=_stage_writer(settings, "optimize"),
        space_guard=_migration_space_guard(settings, int(budget["safety_reserve_bytes"])),
    )
    index_result = build_index_from_manifest(
        target_root,
        _analysis_manifest(settings),
        _index_path(settings, target_root),
        conversion_manifest=target_root / CONVERSION_MANIFEST,
    )
    payload = {
        **result.as_dict(),
        "index": index_result.as_dict(),
        "completed_at": _now(),
    }
    _write_operation(settings, state="complete", operation="optimize", phase="complete", percent=100, result=payload)
    return payload


def _incremental_candidates(index_path: Path) -> list[str]:
    if not index_path.is_file():
        raise MediaOptimizationWorkflowError("Сначала проверьте новые изображения")
    with closing(sqlite3.connect(index_path)) as connection:
        return [
            str(row[0])
            for row in connection.execute(
                "select relative_path from media_objects "
                "where status != 'missing' and decision = 'jpeg_candidate' "
                "order by relative_path collate nocase"
            )
        ]


def _incremental_target(relative_path: str, occupied: set[str]) -> str:
    path = Path(relative_path)
    if path.suffix.casefold() in {".jpg", ".jpeg", ".jpe", ".jfif"}:
        return relative_path
    candidate = path.with_suffix(".jpg").as_posix()
    if candidate.casefold() in occupied:
        suffix = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:10]
        candidate = path.with_name(f"{path.stem}.optimized-{suffix}.jpg").as_posix()
    return candidate


def _replace_incremental_references(database: Path, old_path: str, new_path: str) -> int:
    if old_path == new_path:
        return 0
    updates = 0
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("begin immediate")
        for table, column, rowid, raw_value in list(_reference_rows(connection)):
            normalized, state = normalize_reference(raw_value)
            if state != "managed" or normalized is None or normalized.casefold() != old_path.casefold():
                continue
            connection.execute(
                f"update {quoted_identifier(table)} set {quoted_identifier(column)} = ? where rowid = ?",
                (new_path, rowid),
            )
            updates += 1
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return updates


def _incremental_health_check(data_root: Path, database: Path) -> dict[str, object]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    missing = external = 0
    try:
        integrity = str(connection.execute("pragma integrity_check").fetchone()[0])
        foreign_keys = len(connection.execute("pragma foreign_key_check").fetchall())
        for _, _, _, raw_value in _reference_rows(connection):
            normalized, state = normalize_reference(raw_value)
            if normalized is None and isinstance(raw_value, str) and raw_value.strip():
                external += 1
            elif state == "managed" and normalized and not (data_root / Path(normalized)).is_file():
                missing += 1
    finally:
        connection.close()
    passed = integrity == "ok" and foreign_keys == 0 and missing == 0 and external == 0
    return {
        "passed": passed,
        "integrity_check": integrity,
        "foreign_key_violations": foreign_keys,
        "missing_referenced_paths": missing,
        "external_references": external,
        "incremental_checked_at": _now(),
    }


def run_incremental_optimize(settings: Settings) -> dict[str, object]:
    active = settings.rewards_data_dir.resolve()
    target = _target_root(settings)
    if active != target or _workspace_pointer(settings).get("mode") != "optimized":
        raise MediaOptimizationWorkflowError("Обработка новых изображений доступна только для рабочей оптимизированной копии")
    index_path = _index_path(settings, active)
    candidates = _incremental_candidates(index_path)
    if not candidates:
        raise MediaOptimizationWorkflowError("Новых или изменённых изображений для оптимизации нет")

    occupied = {entry.relative_path.casefold() for entry in inventory_files(active)}
    converted = updated_references = saved_bytes = 0
    converted_paths: list[str] = []
    started = time.perf_counter()
    progress = _progress_writer(settings, "incremental_optimize", "optimizing_images")
    _write_operation(
        settings,
        state="running",
        operation="incremental_optimize",
        phase="optimizing_images",
        phase_label=PHASE_LABELS["optimizing_images"],
        processed=0,
        total=len(candidates),
        percent=0,
    )
    try:
        for index, relative_path in enumerate(candidates, start=1):
            if _is_cancelled(settings):
                raise InterruptedError("incremental media optimization cancelled")
            source_path = (active / Path(relative_path)).resolve()
            if active not in source_path.parents or not source_path.is_file():
                raise MediaOptimizationWorkflowError(f"Файл для оптимизации не найден: {relative_path}")
            target_relative = _incremental_target(relative_path, occupied)
            target_path = (active / Path(target_relative)).resolve()
            if active not in target_path.parents:
                raise MediaOptimizationWorkflowError("Небезопасный путь incremental optimization")
            source_size = source_path.stat().st_size
            target_size, _ = _convert_png(source_path, target_path, ConversionPolicy())
            try:
                updated_references += _replace_incremental_references(
                    settings.rewards_db_path.resolve(),
                    relative_path,
                    target_relative,
                )
            except Exception:
                if target_path != source_path:
                    target_path.unlink(missing_ok=True)
                raise
            if target_path != source_path:
                source_path.unlink(missing_ok=True)
                occupied.discard(relative_path.casefold())
                occupied.add(target_relative.casefold())
            converted += 1
            converted_paths.append(target_relative)
            saved_bytes += max(0, source_size - target_size)
            progress(index, len(candidates))
    except BaseException:
        run_incremental_index(active, index_path, database=settings.rewards_db_path.resolve())
        raise

    _stage_writer(settings, "incremental_optimize")("checking_health")
    index_result = run_incremental_index(active, index_path, database=settings.rewards_db_path.resolve())
    health = {
        **(_read_json(target / HEALTH_REPORT) or {}),
        **_incremental_health_check(active, settings.rewards_db_path.resolve()),
    }
    _write_json(target / HEALTH_REPORT, health)
    if not health["passed"]:
        raise OptimizationError("incremental optimized copy health check failed")
    payload = {
        "mode": "incremental_optimize",
        "converted": converted,
        "updated_references": updated_references,
        "saved_bytes": saved_bytes,
        "converted_paths": converted_paths,
        "health": health,
        "index": index_result.as_dict(),
        "elapsed_seconds": time.perf_counter() - started,
        "completed_at": _now(),
    }
    _write_json(_state_dir(settings) / LAST_CHECK, {"mode": "delta", **index_result.as_dict(), "completed_at": _now()})
    _write_operation(
        settings,
        state="complete",
        operation="incremental_optimize",
        phase="complete",
        phase_label=PHASE_LABELS["complete"],
        percent=100,
        result=payload,
    )
    return payload


def _interrupted_message(operation_name: str) -> str:
    if operation_name == "optimize":
        return (
            "Оптимизация остановлена безопасно. Незавершённую копию нельзя продолжить пофайлово; "
            "её можно удалить и создать заново."
        )
    if operation_name == "incremental_optimize":
        return "Операция остановлена безопасно. Уже обработанные файлы сохранены; продолжите с оставшихся файлов."
    return "Проверка остановлена безопасно. Запустите проверку заново."


def _failure_details(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, MediaOptimizationInsufficientSpaceError):
        required_gb = exc.required / 1_000_000_000
        available_gb = exc.available / 1_000_000_000
        missing_gb = max(0, exc.required - exc.available) / 1_000_000_000
        return (
            "insufficient_space",
            "Недостаточно свободного места для безопасной оптимизации. "
            f"Требуется не менее {required_gb:.1f} ГБ, доступно {available_gb:.1f} ГБ. "
            f"Освободите ещё минимум {missing_gb:.1f} ГБ и повторите проверку.",
        )
    if isinstance(exc, MediaOptimizationMissingReferenceError):
        return "missing_reference_placeholder", str(exc)
    if isinstance(exc, OptimizationTargetNotWritableError):
        return (
            "target_not_writable",
            "Не удалось создать оптимизированную копию: папка назначения защищена от записи. "
            "Проверьте права на папку или выберите доступное расположение.",
        )
    if isinstance(exc, PermissionError) and getattr(exc, "winerror", None) == 32:
        return (
            "file_busy",
            "Файл занят другой программой. Закройте окно просмотра этого файла и повторите попытку.",
        )
    if isinstance(exc, PermissionError):
        return (
            "access_denied",
            "Нет доступа к нужному каталогу или файлу. Проверьте права на рабочую папку.",
        )
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == errno.ENOSPC:
        return "insufficient_space", "Недостаточно свободного места для создания оптимизированной копии."
    if isinstance(exc, OptimizationError) and "analysis manifest does not match" in str(exc):
        return (
            "source_changed_after_check",
            "Состав исходных изображений изменился после проверки. Выполните «Проверить» ещё раз.",
        )
    if isinstance(exc, FileNotFoundError):
        return "path_error", "Не найден необходимый файл или каталог. Повторите проверку базы."
    if isinstance(exc, OptimizationError) and "health check failed" in str(exc):
        return (
            "health_check_failed",
            "Проверка базы или изображений не пройдена. Незавершённая копия не будет активирована.",
        )
    if isinstance(exc, OptimizationError):
        return "media_error", str(exc).strip() or "Не удалось обработать одно из изображений."
    if isinstance(exc, OSError):
        return "filesystem_error", "Файловая система не смогла завершить операцию. Повторите попытку."
    message = str(exc).strip()
    return "operation_failed", message or "Операция завершилась с ошибкой."


def _normalize_legacy_operation_error(operation: dict[str, object]) -> dict[str, object]:
    if (
        operation.get("state") == "error"
        and operation.get("operation") == "optimize"
        and operation.get("error_type") == "PermissionError"
        and ".optimization-incomplete" in str(operation.get("message") or "")
    ):
        return {
            **operation,
            "error_code": "target_not_writable",
            "message": (
                "Не удалось создать оптимизированную копию: папка назначения защищена от записи. "
                "Новая попытка будет использовать доступное расположение."
            ),
        }
    return operation


def _background(settings: Settings, operation_name: str, callback: Callable[[], dict[str, object]]) -> None:
    key = _operation_key(settings)
    try:
        callback()
    except InterruptedError:
        _write_operation(
            settings,
            state="cancelled",
            operation=operation_name,
            phase="stopped_safely",
            percent=0,
            message=_interrupted_message(operation_name),
        )
    except Exception as exc:
        error_code, message = _failure_details(exc)
        current = _read_json(_state_dir(settings) / OPERATION_STATUS) or {}
        failed_phase = str(current.get("phase") or "error")
        _write_operation(
            settings,
            state="error",
            operation=operation_name,
            phase=failed_phase,
            phase_label=PHASE_LABELS.get(failed_phase, "Операция остановлена"),
            percent=0,
            error_type=type(exc).__name__,
            error_code=error_code,
            message=message,
        )
    finally:
        with _operations_lock:
            _operations.pop(key, None)


def _start(settings: Settings, operation_name: str, callback: Callable[[], dict[str, object]]) -> None:
    key = _operation_key(settings)
    with _operations_lock:
        active = _operations.get(key)
        if active is not None and active.thread.is_alive():
            raise MediaOptimizationWorkflowError("Операция уже выполняется")
        cancel = threading.Event()
        thread = threading.Thread(
            target=_background,
            args=(settings, operation_name, callback),
            name=f"media-optimization-{operation_name}",
            daemon=True,
        )
        _operations[key] = _ActiveOperation(thread=thread, cancel=cancel)
        initial_phase = INITIAL_OPERATION_PHASES[operation_name]
        try:
            # The POST contract is observable: status must be durable before the
            # worker can be delayed by Windows thread scheduling.
            _write_operation(
                settings,
                state="running",
                operation=operation_name,
                phase=initial_phase,
                phase_label=PHASE_LABELS[initial_phase],
                processed=0,
                total=0,
                percent=0,
            )
            thread.start()
        except Exception as exc:
            _operations.pop(key, None)
            _, message = _failure_details(exc)
            raise MediaOptimizationWorkflowError(message) from exc


def start_check(settings: Settings) -> None:
    _start(settings, "check", lambda: run_check(settings))


def start_optimize(settings: Settings, *, restart_incomplete: bool = False) -> None:
    _require_optimization_space(_optimization_space_budget(settings))
    _require_reference_repair_ready(settings)
    _start(
        settings,
        "optimize",
        lambda: run_optimize(settings, restart_incomplete=restart_incomplete),
    )


def start_incremental_optimize(settings: Settings) -> None:
    if settings.rewards_data_dir.resolve() != _target_root(settings):
        raise MediaOptimizationWorkflowError("Обработка новых изображений доступна только для рабочей оптимизированной копии")
    if not _incremental_candidates(_index_path(settings, settings.rewards_data_dir.resolve())):
        raise MediaOptimizationWorkflowError("Новых или изменённых изображений для оптимизации нет")
    _start(settings, "incremental_optimize", lambda: run_incremental_optimize(settings))


def cancel_operation(settings: Settings) -> bool:
    key = _operation_key(settings)
    with _operations_lock:
        active = _operations.get(key)
        if active is None or not active.thread.is_alive():
            return False
        active.cancel.set()
    return True


def _verified_target(settings: Settings) -> Path:
    target = _target_root(settings)
    status = _read_json(target / STATUS_FILE) or {}
    health = _read_json(target / HEALTH_REPORT) or {}
    if not (target / COMPLETE_MARKER).is_file() or status.get("state") != "complete" or not health.get("passed"):
        raise MediaOptimizationWorkflowError("Оптимизированная копия не прошла полную проверку")
    return target


def _workspace_pointer(settings: Settings) -> dict[str, object]:
    return _read_json(_state_dir(settings) / ACTIVE_WORKSPACE) or {}


def preview_optimized_workspace(settings: Settings) -> None:
    target = _verified_target(settings)
    _write_json(
        _state_dir(settings) / ACTIVE_WORKSPACE,
        {
            "workspace": str(target),
            "source": str(_source_root(settings)),
            "mode": "preview",
            "previewed_at": _now(),
            "snapshot_created_at": _file_mtime(target / STATUS_FILE),
            "policy_version": JPEG_POLICY_VERSION,
        },
    )


def activate_optimized_workspace(settings: Settings) -> None:
    target = _verified_target(settings)
    pointer = _workspace_pointer(settings)
    if Path(str(pointer.get("workspace") or "")).resolve() != target or pointer.get("mode") != "preview":
        raise MediaOptimizationWorkflowError("Сначала откройте оптимизированную копию для проверки")
    _write_json(
        _state_dir(settings) / ACTIVE_WORKSPACE,
        {
            **pointer,
            "workspace": str(target),
            "source": str(_source_root(settings)),
            "mode": "optimized",
            "activated_at": _now(),
            "policy_version": JPEG_POLICY_VERSION,
        },
    )


def activate_source_workspace(settings: Settings, *, confirm_snapshot_rollback: bool = False) -> None:
    pointer = _workspace_pointer(settings)
    if pointer.get("mode") == "optimized" and not confirm_snapshot_rollback:
        raise MediaOptimizationWorkflowError(
            "Подтвердите возврат к сохранённой исходной копии: более поздние изменения в ней отсутствуют"
        )
    (_state_dir(settings) / ACTIVE_WORKSPACE).unlink(missing_ok=True)


def _index_summary(index_path: Path) -> dict[str, object]:
    if not index_path.is_file():
        return {"exists": False, "indexed": 0, "bytes": 0, "missing": 0, "candidates": 0}
    with closing(sqlite3.connect(index_path)) as connection:
        indexed, total_bytes, missing, candidates = connection.execute(
            "select count(*), "
            "coalesce(sum(case when status != 'missing' then size else 0 end), 0), "
            "sum(case when status = 'missing' then 1 else 0 end), "
            "sum(case when status != 'missing' and decision = 'jpeg_candidate' then 1 else 0 end) "
            "from media_objects"
        ).fetchone()
        metadata = {
            key: json.loads(value)
            for key, value in connection.execute(
                "select key, value from metadata where key in ('last_run_at', 'last_run_state', 'policy_version')"
            )
        }
    return {
        "exists": True,
        "indexed": int(indexed),
        "bytes": int(total_bytes),
        "missing": int(missing or 0),
        "candidates": int(candidates or 0),
        **metadata,
    }


def _available_bytes(path: Path) -> int:
    candidate = path.resolve()
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    try:
        return int(shutil.disk_usage(candidate).free)
    except OSError:
        return 0


def _estimated_required_bytes(
    predicted_target_bytes: int,
    database_bytes: int,
) -> tuple[int, int, str]:
    if not predicted_target_bytes:
        return 0, 0, "full-copy-conservative"
    support_bytes = max(0, database_bytes) + SPACE_SERVICE_OVERHEAD_BYTES
    # Budget for the complete logical copy even when same-volume hardlinks are
    # available. The transfer layer may safely fall back to a physical copy.
    return predicted_target_bytes + support_bytes, support_bytes, "full-copy-conservative"


def _optimization_space_budget(settings: Settings) -> dict[str, int | str | bool]:
    analysis = _read_json(_analysis_summary(settings))
    forecast = dict((analysis or {}).get("quality_forecasts", {}).get("90") or {})
    predicted_target_bytes = int(forecast.get("predicted_total_bytes") or 0)
    try:
        database_bytes = settings.rewards_db_path.resolve().stat().st_size
    except OSError:
        database_bytes = 0
    additional, support, strategy = _estimated_required_bytes(
        predicted_target_bytes,
        database_bytes,
    )
    reserve = (additional * SPACE_RESERVE_PERCENT + 99) // 100 if additional else 0
    required = additional + reserve
    available = _available_bytes(_target_root(settings).parent)
    shortfall = max(0, required - available)
    return {
        "estimated_additional_bytes": additional,
        "database_copy_bytes": database_bytes,
        "service_overhead_bytes": SPACE_SERVICE_OVERHEAD_BYTES if predicted_target_bytes else 0,
        "copy_support_bytes": support,
        "safety_reserve_bytes": reserve,
        "required_free_space_bytes": required,
        "available_bytes": available,
        "space_shortfall_bytes": shortfall,
        "space_strategy": strategy,
        "space_ok": bool(required and available >= required),
    }


def _reference_repair_status(settings: Settings) -> dict[str, object]:
    analysis = _read_json(_analysis_summary(settings)) or {}
    references = dict(analysis.get("references") or {})
    missing = int(references.get("missing_reference_occurrences") or 0)
    unique = int(references.get("missing_reference_unique_paths") or missing)
    groups = references.get("missing_reference_groups")
    if not isinstance(groups, list):
        groups = []
    if not missing:
        ready = True
    elif "missing_reference_repair_ready" in references:
        ready = bool(references.get("missing_reference_repair_ready"))
    else:
        ready = (_source_root(settings) / MISSING_REFERENCE_PLACEHOLDER).is_file()
    return {
        "missing_references": missing,
        "missing_reference_unique_paths": unique,
        "missing_reference_groups": groups,
        "reference_repair_placeholder": str(
            references.get("missing_reference_placeholder") or MISSING_REFERENCE_PLACEHOLDER
        ),
        "reference_repair_ready": ready,
        "reference_repair_blocking": bool(missing and not ready),
    }


def _require_reference_repair_ready(settings: Settings) -> None:
    status = _reference_repair_status(settings)
    if status["reference_repair_blocking"]:
        raise MediaOptimizationMissingReferenceError(
            "В базе есть ссылки на отсутствующие изображения, но стандартное изображение «Нет фото» "
            "не найдено или не читается. Восстановите стандартное изображение и повторите проверку."
        )


def _require_optimization_space(budget: dict[str, int | str | bool]) -> None:
    required = int(budget["required_free_space_bytes"])
    available = int(budget["available_bytes"])
    if required <= 0:
        raise MediaOptimizationWorkflowError("Сначала выполните проверку исходных изображений")
    if available < required:
        raise MediaOptimizationInsufficientSpaceError(required, available)


def _migration_space_guard(settings: Settings, safety_reserve_bytes: int) -> Callable[[int, int], None]:
    def check(processed: int, total: int) -> None:
        if processed not in {0, total} and processed % SPACE_GUARD_INTERVAL:
            return
        available = _available_bytes(_target_root(settings).parent)
        if available < safety_reserve_bytes:
            raise MediaOptimizationInsufficientSpaceError(safety_reserve_bytes, available)

    return check


def _file_mtime(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    except OSError:
        return None


def workflow_snapshot(settings: Settings) -> dict[str, object]:
    state_dir = _state_dir(settings)
    source = _source_root(settings)
    target = _target_root(settings)
    active = settings.rewards_data_dir.resolve()
    pointer = _workspace_pointer(settings)
    operation = _normalize_legacy_operation_error(
        _read_json(state_dir / OPERATION_STATUS) or {"state": "idle"}
    )
    if operation.get("state") == "running" and not _operation_running(settings):
        operation = {
            **operation,
            "state": "interrupted",
            "message": _interrupted_message(str(operation.get("operation") or "")),
        }
    operation = {
        **operation,
        "phase_label": PHASE_LABELS.get(
            str(operation.get("phase") or ""),
            str(operation.get("phase_label") or "Ожидание"),
        ),
    }
    analysis = _read_json(_analysis_summary(settings))
    baseline_exists = bool(analysis)
    target_status = _read_json(target / STATUS_FILE)
    health = _read_json(target / HEALTH_REPORT)
    last_check = _read_json(state_dir / LAST_CHECK)
    current_index = _index_summary(_index_path(settings, active))
    source_index = _index_summary(_index_path(settings, source))
    optimized_index = _index_summary(_index_path(settings, target))
    forecast: dict[str, object] = {}
    if analysis:
        forecast = dict((analysis.get("quality_forecasts") or {}).get("90") or {})
    target_result = dict((target_status or {}).get("result") or {})
    inventory = dict((analysis or {}).get("inventory") or {})
    last_delta = dict(last_check or {})
    changed_count = int(last_delta.get("new") or 0) + int(last_delta.get("changed") or 0)
    predicted_target_bytes = int(forecast.get("predicted_total_bytes") or 0)
    target_bytes = int(target_result.get("destination_bytes") or optimized_index.get("bytes") or 0)
    target_incomplete = bool(
        target_status
        and target_status.get("state") == "incomplete"
        and (target / INCOMPLETE_MARKER).is_file()
    )
    target_complete = bool((target / COMPLETE_MARKER).is_file() and target_status and target_status.get("state") == "complete")
    budget = _optimization_space_budget(settings)
    reference_status = _reference_repair_status(settings)
    current_bytes = (
        int(current_index.get("bytes") or 0)
        if current_index.get("exists")
        else int(inventory.get("bytes") or 0) if analysis else None
    )
    pointer_mode = str(pointer.get("mode") or "optimized") if active == target else "source"
    workspace_state = pointer_mode if pointer_mode in {"preview", "optimized"} else "source"
    classifications = dict(dict((analysis or {}).get("records") or {}).get("classifications") or {})
    candidate_summary = dict(classifications.get("jpeg_candidate") or {})
    warning_files = sum(
        int(dict(values).get("files") or 0)
        for name, values in classifications.items()
        if str(name).startswith(("corrupt", "unsupported", "extension_mismatch"))
    )
    snapshot_created_at = _file_mtime(target / STATUS_FILE)
    source_status = "Рабочая" if workspace_state == "source" else "Резервная"
    if workspace_state == "preview":
        target_workspace_status = "Проверка"
    elif workspace_state == "optimized":
        target_workspace_status = "Рабочая"
    elif target_incomplete:
        target_workspace_status = "Незавершённая"
    elif target_complete and health and health.get("passed"):
        target_workspace_status = "Готова"
    elif target_status:
        target_workspace_status = "Ошибка"
    else:
        target_workspace_status = "Не создана"
    workspaces = [
        {
            "key": "source",
            "label": "Исходная до оптимизации" if target_status else "Текущая рабочая база",
            "status": source_status,
            "created_at": snapshot_created_at or _file_mtime(settings.rewards_db_path),
            "bytes": int(inventory.get("bytes") or target_result.get("source_bytes") or 0),
            "optimization_status": "Не оптимизирована" if baseline_exists else "Не проверено",
            "active": workspace_state == "source",
        }
    ]
    if target_status or target_complete:
        workspaces.append(
            {
                "key": "optimized",
                "label": f"Оптимизированная {snapshot_created_at[:10] if snapshot_created_at else ''}".strip(),
                "status": target_workspace_status,
                "created_at": snapshot_created_at,
                "bytes": target_bytes,
                "optimization_status": "Оптимизирована" if target_complete else "Не завершена",
                "active": workspace_state in {"preview", "optimized"},
            }
        )
    resume_available = bool(
        operation.get("operation") in {"check", "incremental_optimize"}
        and operation.get("state") in {"interrupted", "error"}
        and current_index.get("exists")
    )
    return {
        "source_workspace": str(source),
        "target_workspace": str(target),
        "active_workspace": str(active),
        "workspace_state": workspace_state,
        "workspace_label": (
            "Оптимизированная копия: режим проверки"
            if workspace_state == "preview"
            else "Рабочая база оптимизирована"
            if workspace_state == "optimized"
            else "Текущая рабочая база"
        ),
        "workspace_optimization_status": (
            "Оптимизирована"
            if workspace_state in {"preview", "optimized"}
            else "Не оптимизирована"
            if baseline_exists
            else "Не проверено"
        ),
        "workspaces": workspaces,
        "operation": operation,
        "analysis": analysis,
        "baseline_exists": baseline_exists,
        "baseline_at": _file_mtime(_analysis_summary(settings)),
        "current_index": current_index,
        "source_index": source_index,
        "optimized_index": optimized_index,
        "last_check": last_check,
        "source_bytes": int(inventory.get("bytes") or target_result.get("source_bytes") or 0),
        "current_bytes": current_bytes,
        "predicted_saved_bytes": int(forecast.get("predicted_saved_bytes") or 0),
        "predicted_target_bytes": predicted_target_bytes,
        "candidate_files": int(candidate_summary.get("files") or 0),
        "warning_files": warning_files,
        **reference_status,
        **budget,
        "estimated_required_bytes": int(budget["required_free_space_bytes"]),
        "estimated_space_ok": bool(target_complete or budget["space_ok"]),
        "safe_copy_ready": bool(
            target_complete
            or (budget["space_ok"] and not reference_status["reference_repair_blocking"])
        ),
        "new_files": int(last_delta.get("new") or 0),
        "changed_files": int(last_delta.get("changed") or 0),
        "delta_files": changed_count,
        "decoded_files": int(last_delta.get("decoded") or 0),
        "target_status": target_status,
        "target_complete": target_complete,
        "target_result": target_result,
        "target_bytes": target_bytes,
        "actual_saved_bytes": int(target_result.get("saved_bytes") or 0),
        "converted_files": int(target_result.get("converted") or 0),
        "skipped_files": int(target_result.get("skipped") or target_result.get("kept") or 0),
        "error_files": int(target_result.get("errors") or 0),
        "last_optimization_at": _file_mtime(target / STATUS_FILE),
        "health": health,
        "health_passed": bool(health and health.get("passed")),
        "conversion_manifest_exists": (target / CONVERSION_MANIFEST).is_file(),
        "can_preview": bool(target_complete and health and health.get("passed") and workspace_state == "source"),
        "can_activate": bool(target_complete and health and health.get("passed") and workspace_state == "preview"),
        "can_return_from_preview": workspace_state == "preview",
        "rollback_confirmation_required": workspace_state == "optimized",
        "snapshot_created_at": snapshot_created_at,
        "target_incomplete": target_incomplete,
        "resume_available": resume_available,
        "restart_available": target_incomplete,
        "retry_available": bool(
            operation.get("operation") == "optimize"
            and operation.get("state") == "error"
            and not target_incomplete
        ),
        "incremental_mode": workspace_state == "optimized",
        "incremental_candidate_files": int(current_index.get("candidates") or 0),
        "running": _operation_running(settings),
    }
