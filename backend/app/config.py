from pathlib import Path
from typing import Optional
import os

from dotenv import load_dotenv
from pydantic import BaseModel


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


class Settings(BaseModel):
    rewards_data_dir: Path
    rewards_db_path: Path
    app_host: str = "127.0.0.1"
    app_port: int = 8080
    read_only: bool = False
    write_mode: bool = True
    update_check_enabled: bool = True
    update_manifest_url: str = "https://github.com/drthalas/Fedorinov_rewards/releases/latest/download/latest.json"
    update_timeout_seconds: int = 10
    app_install_dir: Path = PROJECT_ROOT
    update_backup_dir: Path = PROJECT_ROOT / "updates" / "backups"
    update_download_dir: Path = PROJECT_ROOT / "updates" / "downloads"
    update_extract_dir: Path = PROJECT_ROOT / "updates" / "extracted"

    @property
    def data_dir_exists(self) -> bool:
        return self.rewards_data_dir.exists() and self.rewards_data_dir.is_dir()

    @property
    def db_exists(self) -> bool:
        return self.rewards_db_path.exists() and self.rewards_db_path.is_file()

    def validation_errors(self) -> list[str]:
        errors: list[str] = []
        if not self.data_dir_exists:
            errors.append(f"REWARDS_DATA_DIR does not exist: {self.rewards_data_dir}")
        if not self.db_exists:
            errors.append(f"Rewards database does not exist: {self.rewards_db_path}")
        if self.write_mode and self.read_only:
            errors.append("Для редактирования нужно выключить режим просмотра: READ_ONLY=false.")
        return errors

    @property
    def source_dir(self) -> Path:
        return self.rewards_data_dir / "Source"

    @property
    def source_mark_dir(self) -> Path:
        return self.rewards_data_dir / "SourceMark"

    @property
    def default_dir(self) -> Path:
        return self.rewards_data_dir / "default"

    @property
    def guide_images_dir(self) -> Path:
        return self.rewards_data_dir / "GuideImages"

    @property
    def nofoto_path(self) -> Path:
        return self.default_dir / "nofoto.jpg"


def _env_path(name: str, default: Optional[str] = None) -> Path:
    value = os.getenv(name, default)
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return Path(os.path.expandvars(value)).expanduser()


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"true", "1", "yes", "on"}


def _env_int(name: str, default: str) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return int(default)


def _env_path_relative_to(name: str, base: Path, default: str) -> Path:
    raw_value = os.getenv(name, default).strip()
    expanded = Path(os.path.expandvars(raw_value)).expanduser()
    if expanded.is_absolute():
        return expanded
    return base / expanded


def _env_optional_path(name: str, default: Path) -> Path:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    return Path(os.path.expandvars(raw_value)).expanduser()


def get_settings() -> Settings:
    data_dir = _env_path("REWARDS_DATA_DIR", "/Users/hermes/Desktop/Rewards")
    db_path = _env_path(
        "REWARDS_DB_PATH",
        str(data_dir / "database" / "MyDatabase.sqlite"),
    )
    app_install_dir = _env_optional_path("APP_INSTALL_DIR", PROJECT_ROOT)
    return Settings(
        rewards_data_dir=data_dir,
        rewards_db_path=db_path,
        app_host=os.getenv("APP_HOST", "127.0.0.1"),
        app_port=_env_int("APP_PORT", "8080"),
        read_only=_env_bool("READ_ONLY", "false"),
        write_mode=_env_bool("WRITE_MODE", "true"),
        update_check_enabled=_env_bool("UPDATE_CHECK_ENABLED", "true"),
        update_manifest_url=os.getenv(
            "UPDATE_MANIFEST_URL",
            "https://github.com/drthalas/Fedorinov_rewards/releases/latest/download/latest.json",
        ).strip(),
        update_timeout_seconds=_env_int("UPDATE_TIMEOUT_SECONDS", "10"),
        app_install_dir=app_install_dir,
        update_backup_dir=_env_path_relative_to("UPDATE_BACKUP_DIR", app_install_dir, "updates/backups"),
        update_download_dir=_env_path_relative_to("UPDATE_DOWNLOAD_DIR", app_install_dir, "updates/downloads"),
        update_extract_dir=_env_path_relative_to("UPDATE_EXTRACT_DIR", app_install_dir, "updates/extracted"),
    )
