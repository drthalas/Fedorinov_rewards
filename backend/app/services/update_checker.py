from __future__ import annotations

import json
from typing import Callable
import urllib.error
import urllib.request

from ..config import Settings
from ..version import APP_VERSION


ManifestFetcher = Callable[[str, int], bytes]


def parse_semver(version: object) -> tuple[int, int, int] | None:
    parts = str(version or "").strip().split(".")
    if len(parts) != 3:
        return None
    try:
        parsed = tuple(int(part) for part in parts)
    except ValueError:
        return None
    if any(part < 0 for part in parsed):
        return None
    return parsed  # type: ignore[return-value]


def is_newer_version(latest_version: object, current_version: object = APP_VERSION) -> bool:
    latest = parse_semver(latest_version)
    current = parse_semver(current_version)
    if latest is None or current is None:
        raise ValueError("Некорректный формат версии")
    return latest > current


def fetch_manifest(url: str, timeout_seconds: int) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "FedorinovRewardsUpdateChecker/0.1",
            "Cache-Control": "no-cache, no-store",
            "Pragma": "no-cache",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return response.read()


def _base_result(settings: Settings, current_version: str) -> dict[str, object]:
    return {
        "enabled": settings.update_check_enabled,
        "update_available": False,
        "current_version": current_version,
        "latest_version": None,
        "released_at": None,
        "notes": [],
        "download_url": None,
        "sha256": None,
        "error": None,
    }


def check_for_updates(
    settings: Settings,
    current_version: str = APP_VERSION,
    fetcher: ManifestFetcher | None = None,
) -> dict[str, object]:
    result = _base_result(settings, current_version)
    if not settings.update_check_enabled:
        return result

    manifest_url = settings.update_manifest_url.strip()
    if not manifest_url:
        result["error"] = "Не указан адрес проверки обновлений."
        return result

    timeout_seconds = max(1, int(settings.update_timeout_seconds or 10))
    try:
        raw_manifest = (fetcher or fetch_manifest)(manifest_url, timeout_seconds)
        manifest = json.loads(raw_manifest.decode("utf-8"))
    except json.JSONDecodeError:
        result["error"] = "Не удалось проверить обновления: получен некорректный JSON."
        return result
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        result["error"] = f"Не удалось проверить обновления: {exc}"
        return result

    latest_version = str(manifest.get("version") or "").strip()
    if not latest_version:
        result["error"] = "Не удалось проверить обновления: в manifest нет version."
        return result

    try:
        update_available = is_newer_version(latest_version, current_version)
    except ValueError:
        result["error"] = "Не удалось проверить обновления: некорректный формат версии."
        return result

    notes = manifest.get("notes") or []
    if not isinstance(notes, list):
        notes = []

    result.update(
        {
            "update_available": update_available,
            "latest_version": latest_version,
            "released_at": manifest.get("released_at"),
            "notes": [str(note) for note in notes if str(note).strip()],
            "download_url": manifest.get("download_url"),
            "sha256": manifest.get("sha256"),
        }
    )
    return result
