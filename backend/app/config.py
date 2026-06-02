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
        app_port=int(os.getenv("APP_PORT", "8080")),
        read_only=os.getenv("READ_ONLY", "true").lower() == "true",
        write_mode=os.getenv("WRITE_MODE", "false").lower() == "true",
        require_backup_before_write=os.getenv("REQUIRE_BACKUP_BEFORE_WRITE", "true").lower() == "true",
    )
