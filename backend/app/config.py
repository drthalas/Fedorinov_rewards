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
    read_only: bool = True
    write_mode: bool = False
    require_backup_before_write: bool = True
    update_check_enabled: bool = True
    update_manifest_url: str = "https://github.com/drthalas/Fedorinov_rewards/releases/latest/download/latest.json"
    update_timeout_seconds: int = 10

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
            errors.append("WRITE_MODE=true requires READ_ONLY=false for future write routes")
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


def get_settings() -> Settings:
    data_dir = _env_path("REWARDS_DATA_DIR", "/Users/hermes/Desktop/Rewards")
    db_path = _env_path(
        "REWARDS_DB_PATH",
        str(data_dir / "database" / "MyDatabase.sqlite"),
    )
    return Settings(
        rewards_data_dir=data_dir,
        rewards_db_path=db_path,
        app_host=os.getenv("APP_HOST", "127.0.0.1"),
        app_port=_env_int("APP_PORT", "8080"),
        read_only=_env_bool("READ_ONLY", "true"),
        write_mode=_env_bool("WRITE_MODE", "false"),
        require_backup_before_write=_env_bool("REQUIRE_BACKUP_BEFORE_WRITE", "true"),
        update_check_enabled=_env_bool("UPDATE_CHECK_ENABLED", "true"),
        update_manifest_url=os.getenv(
            "UPDATE_MANIFEST_URL",
            "https://github.com/drthalas/Fedorinov_rewards/releases/latest/download/latest.json",
        ).strip(),
        update_timeout_seconds=_env_int("UPDATE_TIMEOUT_SECONDS", "10"),
    )
