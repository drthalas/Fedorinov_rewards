from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sys


AUDIT_ROOT = Path.home() / "LocalData" / "FedorinovRewards" / "logs"
AUDIT_FILE = AUDIT_ROOT / "dev_audit.log"


def log_action(action: str, entity_type: str, entity_id: object = None, details: dict[str, object] | None = None) -> None:
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "details": details or {},
    }
    try:
        path = audit_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=True, sort_keys=True) + "\n")
    except OSError:
        print(json.dumps(event, ensure_ascii=True, sort_keys=True), file=sys.stdout)


def audit_log_path() -> Path:
    return Path(os.getenv("REWARDS_AUDIT_LOG", str(AUDIT_FILE))).expanduser()
