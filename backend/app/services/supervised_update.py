from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Callable

from ..config import Settings
from ..version import APP_VERSION
from .runtime_identity import process_snapshot, runtime_registry_dir
from .runtime_supervisor import RuntimeLifecycleError, RuntimeSupervisor, read_installed_version
from .updater import (
    UpdateError,
    UpdatePlan,
    build_update_plan,
    copy_package_files,
    create_app_backup,
    download_file,
    extract_update_zip,
    restore_backup,
    sha256_file,
    update_is_running,
    verify_zip_sha256,
    write_update_log,
    write_update_status,
)


@dataclass(frozen=True)
class PreparedUpdate:
    plan: UpdatePlan
    package_root: Path
    backup_path: Path
    zip_path: Path
    verified_sha256: str
    requirements_sha_before: str | None


def install_pinned_dependencies(install_root: Path, python_executable: Path | None = None) -> float:
    python = (python_executable or Path(sys.executable)).expanduser().absolute()
    requirements = install_root / "backend" / "requirements.txt"
    if not requirements.is_file():
        raise UpdateError("В пакете обновления отсутствует backend/requirements.txt.")
    started = time.monotonic()
    try:
        result = subprocess.run(
            [str(python), "-m", "pip", "install", "-r", str(requirements)],
            cwd=install_root,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise UpdateError(f"Не удалось установить зависимости обновления: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        concise = detail[-1] if detail else f"exit {result.returncode}"
        raise UpdateError(f"Не удалось установить зависимости обновления: {concise}")
    return time.monotonic() - started


def prepare_update(
    settings: Settings,
    *,
    current_version: str = APP_VERSION,
    plan_builder: Callable[[Settings, str], UpdatePlan] | None = None,
    zip_downloader=download_file,
) -> PreparedUpdate | UpdatePlan:
    builder = plan_builder or (lambda configured, version: build_update_plan(configured, current_version=version))
    requirements = settings.app_install_dir / "backend" / "requirements.txt"
    requirements_sha_before = sha256_file(requirements) if requirements.is_file() else None
    write_update_status(settings, "running", "checking")
    plan = builder(settings, current_version)
    if not plan.update_available:
        return plan
    if not plan.latest_version or not plan.download_url or not plan.sha256:
        raise UpdateError("В latest.json нет version, download_url или sha256.")

    settings.update_download_dir.mkdir(parents=True, exist_ok=True)
    zip_path = settings.update_download_dir / f"FedorinovRewards_WebPreview_v{plan.latest_version}.zip"
    write_update_status(settings, "running", "downloading")
    zip_downloader(plan.download_url, zip_path, settings.update_timeout_seconds)
    write_update_status(settings, "running", "verifying")
    verified_sha = verify_zip_sha256(zip_path, plan.sha256)
    package_root = extract_update_zip(zip_path, settings.update_extract_dir)
    write_update_status(settings, "running", "backing_up")
    backup_path = create_app_backup(settings)
    return PreparedUpdate(plan, package_root, backup_path, zip_path, verified_sha, requirements_sha_before)


def _install_dependencies_if_changed(
    prepared: PreparedUpdate,
    install_root: Path,
    python_executable: Path,
    dependency_installer,
) -> float:
    requirements = install_root / "backend" / "requirements.txt"
    installed_sha = sha256_file(requirements) if requirements.is_file() else None
    if prepared.requirements_sha_before and installed_sha == prepared.requirements_sha_before:
        return 0.0
    return dependency_installer(install_root, python_executable)


def _confirmed_requester(
    supervisor: RuntimeSupervisor,
    settings: Settings,
    requester_pid: int,
    expected_version: str,
    *,
    require_healthy: bool = True,
):
    for inspection in supervisor.inspect_all():
        record = inspection.record
        if (
            inspection.confirmed
            and (inspection.healthy or not require_healthy)
            and record.pid == requester_pid
            and os.path.normcase(record.install_root)
            == os.path.normcase(str(settings.app_install_dir.resolve(strict=False)))
            and record.host == settings.app_host
            and record.port == settings.app_port
            and record.version == expected_version
        ):
            return inspection
    return None


def _old_processes_are_dead(stopped) -> bool:
    for evidence in stopped:
        snapshot = process_snapshot(evidence.pid)
        if snapshot is not None and snapshot.start_marker == evidence.process_start_marker:
            return False
    return True


def run_supervised_update(
    settings: Settings,
    *,
    requester_pid: int,
    current_version: str = APP_VERSION,
    supervisor: RuntimeSupervisor | None = None,
    plan_builder: Callable[[Settings, str], UpdatePlan] | None = None,
    zip_downloader=download_file,
    dependency_installer=install_pinned_dependencies,
) -> dict[str, object]:
    supervisor = supervisor or RuntimeSupervisor()
    requester = _confirmed_requester(supervisor, settings, requester_pid, current_version)
    if requester is None:
        raise UpdateError(
            "Не удалось подтвердить backend приложения. Запустите программу через start_windows.bat и повторите обновление."
        )

    prepared = prepare_update(
        settings,
        current_version=current_version,
        plan_builder=plan_builder,
        zip_downloader=zip_downloader,
    )
    if isinstance(prepared, UpdatePlan):
        message = "Обновлений нет. Установлена актуальная версия."
        write_update_status(settings, "success", "success", message)
        return {
            "ok": True,
            "update_available": False,
            "current_version": prepared.current_version,
            "latest_version": prepared.latest_version,
            "message": message,
        }

    old_version = requester.record.version
    stopped = []
    install_started = time.monotonic()
    dependency_seconds = 0.0
    new_start = None
    try:
        write_update_status(settings, "running", "stopping")
        stopped = supervisor.stop_all_confirmed()
        if not any(item.pid == requester_pid for item in stopped):
            raise UpdateError("Подтверждённый текущий backend не был завершён; установка остановлена.")

        write_update_status(settings, "running", "installing")
        copied = copy_package_files(prepared.package_root, settings.app_install_dir)
        installed_version = read_installed_version(settings.app_install_dir)
        if installed_version != prepared.plan.latest_version:
            raise UpdateError(
                f"Версия установленного пакета {installed_version} не совпадает с ожидаемой {prepared.plan.latest_version}."
            )

        write_update_status(settings, "running", "dependencies")
        dependency_seconds = _install_dependencies_if_changed(
            prepared,
            settings.app_install_dir,
            supervisor.python_executable,
            dependency_installer,
        )
        write_update_status(settings, "running", "starting")
        new_start = supervisor.start_or_reuse(
            install_root=settings.app_install_dir,
            host=settings.app_host,
            port=settings.app_port,
            expected_version=installed_version,
        )
        if new_start.reused:
            raise UpdateError("После установки был переиспользован старый backend вместо запуска новой версии.")
        if not _old_processes_are_dead(stopped):
            raise UpdateError("После установки один из старых backend PID всё ещё работает.")

        message = "Обновление установлено. Приложение перезапущено и готово к работе."
        result = {
            "ok": True,
            "current_version": old_version,
            "latest_version": installed_version,
            "update_available": True,
            "sha256": prepared.verified_sha256,
            "backup_path": str(prepared.backup_path),
            "copied_files": copied,
            "message": message,
            "old_pids": [item.pid for item in stopped],
            "new_pid": new_start.pid,
            "instance_token": new_start.instance_token,
            "install_root": new_start.install_root,
            "process_timings": {
                "termination_seconds": sum(item.elapsed_seconds for item in stopped),
                "port_release_seconds": new_start.port_release_seconds,
                "readiness_seconds": new_start.readiness_seconds,
                "dependency_seconds": dependency_seconds,
                "install_seconds": time.monotonic() - install_started,
            },
        }
        write_update_log(settings, result)
        write_update_status(settings, "success", "success", message)
        return result
    except Exception as exc:
        rollback_error: Exception | None = None
        rollback_start = None
        try:
            supervisor.stop_all_confirmed()
            restore_backup(prepared.backup_path, settings.app_install_dir)
            restored_version = read_installed_version(settings.app_install_dir)
            if restored_version != old_version:
                raise UpdateError(
                    f"Rollback restored version {restored_version}, expected {old_version}."
                )
            _install_dependencies_if_changed(
                prepared,
                settings.app_install_dir,
                supervisor.python_executable,
                dependency_installer,
            )
            rollback_start = supervisor.start_or_reuse(
                install_root=settings.app_install_dir,
                host=settings.app_host,
                port=settings.app_port,
                expected_version=old_version,
            )
            confirmed = [inspection for inspection in supervisor.inspect_all() if inspection.confirmed and inspection.healthy]
            if len(confirmed) != 1 or confirmed[0].record.pid != rollback_start.pid:
                raise UpdateError("Rollback не восстановил ровно один подтверждённый backend.")
        except Exception as rollback_exc:
            rollback_error = rollback_exc

        if rollback_error is not None:
            message = f"Обновление не удалось; rollback также не завершён: {rollback_error}"
        else:
            message = "Обновление не удалось. Предыдущая версия восстановлена и снова запущена."
        write_update_log(
            settings,
            {
                "ok": False,
                "current_version": old_version,
                "latest_version": prepared.plan.latest_version,
                "error": str(exc),
                "rollback_ok": rollback_error is None,
                "rollback_pid": rollback_start.pid if rollback_start else None,
                "message": message,
            },
        )
        write_update_status(settings, "error", "error", message, str(exc))
        raise UpdateError(message) from exc


def schedule_supervised_update(settings: Settings, *, requester_pid: int | None = None) -> dict[str, object]:
    if not settings.update_check_enabled:
        raise UpdateError("Проверка обновлений выключена.")
    if update_is_running(settings):
        raise UpdateError("Обновление уже выполняется.")

    bootstrap = settings.app_install_dir / "scripts" / "runtime_bootstrap.py"
    if not bootstrap.is_file():
        raise UpdateError("Не найден отдельный update bootstrap; обновление не запущено.")

    registry = runtime_registry_dir()
    owner_pid = requester_pid or os.getpid()
    owner = _confirmed_requester(
        RuntimeSupervisor(registry_dir=registry),
        settings,
        owner_pid,
        APP_VERSION,
        require_healthy=False,
    )
    if owner is None:
        raise UpdateError(
            "Не удалось подтвердить backend приложения. Запустите программу через start_windows.bat и повторите обновление."
        )
    log_dir = registry / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"update-bootstrap-{int(time.time() * 1000)}.log"
    command = [
        sys.executable,
        str(bootstrap),
        "update",
        "--requester-pid",
        str(owner_pid),
    ]
    environment = os.environ.copy()
    environment.update(
        {
            "APP_INSTALL_DIR": str(settings.app_install_dir),
            "APP_HOST": settings.app_host,
            "APP_PORT": str(settings.app_port),
            "APP_RUNTIME_DIR": str(registry),
        }
    )
    creationflags = 0
    start_new_session = os.name != "nt"
    if os.name == "nt":
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    write_update_status(settings, "running", "checking", "Обновление запущено в отдельном процессе.")
    try:
        with log_path.open("ab", buffering=0) as output:
            process = subprocess.Popen(
                command,
                cwd=settings.app_install_dir,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
                start_new_session=start_new_session,
            )
        threading.Thread(target=process.wait, name="update-bootstrap-reaper", daemon=True).start()
    except OSError as exc:
        message = f"Не удалось запустить отдельный update bootstrap: {exc}"
        write_update_status(settings, "error", "error", message, message)
        raise UpdateError(message) from exc

    return {
        "ok": True,
        "scheduled": True,
        "bootstrap_pid": process.pid,
        "current_version": APP_VERSION,
        "message": "Обновление началось. Приложение автоматически перезапустится.",
        "log_path": str(log_path),
    }
