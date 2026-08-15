from __future__ import annotations

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
from .managed_media_analysis import inventory_files, run_analysis
from .media_image_policy import JPEG_POLICY_VERSION
from .media_optimization import (
    COMPLETE_MARKER,
    CONVERSION_MANIFEST,
    HEALTH_REPORT,
    STATUS_FILE,
    build_optimized_copy,
)
from .media_optimization_index import build_index_from_manifest, run_incremental_index


OPERATION_STATUS = "operation-status.json"
ACTIVE_WORKSPACE = "active-workspace.json"
LAST_CHECK = "last-check.json"
ANALYSIS_DIR = "baseline"
SOURCE_INDEX = "source-index.sqlite"
OPTIMIZED_INDEX = "optimized-index.sqlite"


class MediaOptimizationWorkflowError(RuntimeError):
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
            processed=processed,
            total=total,
            percent=percent,
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
            raise MediaOptimizationWorkflowError("Нет данных для восстановления индекса optimized copy")
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
    source_database = source_root / "database" / "MyDatabase.sqlite"
    target_root = _target_root(settings)
    if not _analysis_manifest(settings).is_file():
        raise MediaOptimizationWorkflowError("Сначала выполните проверку исходных изображений")
    _write_operation(settings, state="running", operation="optimize", phase="copy", percent=0)
    result = build_optimized_copy(
        source_root,
        source_database,
        _analysis_manifest(settings),
        target_root,
        restart_incomplete=restart_incomplete,
        progress=_progress_writer(settings, "optimize", "copy"),
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
            message="Операция безопасно остановлена. Её можно продолжить.",
        )
    except Exception as exc:
        _write_operation(
            settings,
            state="error",
            operation=operation_name,
            phase="error",
            percent=0,
            error_type=type(exc).__name__,
            message=str(exc),
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
        thread.start()


def start_check(settings: Settings) -> None:
    _start(settings, "check", lambda: run_check(settings))


def start_optimize(settings: Settings, *, restart_incomplete: bool = False) -> None:
    _start(
        settings,
        "optimize",
        lambda: run_optimize(settings, restart_incomplete=restart_incomplete),
    )


def cancel_operation(settings: Settings) -> bool:
    key = _operation_key(settings)
    with _operations_lock:
        active = _operations.get(key)
        if active is None or not active.thread.is_alive():
            return False
        active.cancel.set()
    return True


def activate_optimized_workspace(settings: Settings) -> None:
    target = _target_root(settings)
    status = _read_json(target / STATUS_FILE) or {}
    health = _read_json(target / HEALTH_REPORT) or {}
    if not (target / COMPLETE_MARKER).is_file() or status.get("state") != "complete" or not health.get("passed"):
        raise MediaOptimizationWorkflowError("Optimized copy не прошла полную проверку")
    _write_json(
        _state_dir(settings) / ACTIVE_WORKSPACE,
        {
            "workspace": str(target),
            "source": str(_source_root(settings)),
            "activated_at": _now(),
            "policy_version": JPEG_POLICY_VERSION,
        },
    )


def activate_source_workspace(settings: Settings) -> None:
    (_state_dir(settings) / ACTIVE_WORKSPACE).unlink(missing_ok=True)


def _index_summary(index_path: Path) -> dict[str, object]:
    if not index_path.is_file():
        return {"exists": False, "indexed": 0, "bytes": 0, "missing": 0}
    with closing(sqlite3.connect(index_path)) as connection:
        indexed, total_bytes, missing = connection.execute(
            "select count(*), "
            "coalesce(sum(case when status != 'missing' then size else 0 end), 0), "
            "sum(case when status = 'missing' then 1 else 0 end) "
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
    operation = _read_json(state_dir / OPERATION_STATUS) or {"state": "idle"}
    if operation.get("state") == "running" and not _operation_running(settings):
        operation = {
            **operation,
            "state": "interrupted",
            "message": "Предыдущая операция была прервана. Её можно продолжить.",
        }
    analysis = _read_json(_analysis_summary(settings))
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
    available_bytes = _available_bytes(target.parent)
    target_incomplete = bool(target_status and target_status.get("state") == "incomplete")
    target_complete = bool((target / COMPLETE_MARKER).is_file() and target_status and target_status.get("state") == "complete")
    current_bytes = (
        int(current_index.get("bytes") or 0)
        if current_index.get("exists")
        else int(inventory.get("bytes") or 0) if analysis else None
    )
    return {
        "source_workspace": str(source),
        "target_workspace": str(target),
        "active_workspace": str(active),
        "workspace_state": "optimized" if active == target else "source",
        "operation": operation,
        "analysis": analysis,
        "baseline_exists": bool(analysis),
        "baseline_at": _file_mtime(_analysis_summary(settings)),
        "current_index": current_index,
        "source_index": source_index,
        "optimized_index": optimized_index,
        "last_check": last_check,
        "source_bytes": int(inventory.get("bytes") or target_result.get("source_bytes") or 0),
        "current_bytes": current_bytes,
        "predicted_saved_bytes": int(forecast.get("predicted_saved_bytes") or 0),
        "predicted_target_bytes": predicted_target_bytes,
        "available_bytes": available_bytes,
        "estimated_space_ok": bool(not predicted_target_bytes or target_complete or available_bytes >= predicted_target_bytes),
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
        "can_activate": bool((target / COMPLETE_MARKER).is_file() and health and health.get("passed")),
        "target_incomplete": target_incomplete,
        "resume_available": bool(target_incomplete or operation.get("state") in {"cancelled", "interrupted", "error"}),
        "running": _operation_running(settings),
    }
