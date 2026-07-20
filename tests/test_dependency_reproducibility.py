from importlib import metadata
from pathlib import Path
from tempfile import TemporaryDirectory
import re
import unittest
from unittest.mock import patch

from scripts import build_windows_preview_package


ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "backend" / "requirements.txt"
PIN_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s]+)$")


def _pinned_requirements() -> dict[str, str]:
    pins: dict[str, str] = {}
    for raw_line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN_PATTERN.fullmatch(line)
        if match is None:
            raise AssertionError(f"Dependency is not exactly pinned: {line}")
        name, version = match.groups()
        normalized = name.casefold().replace("_", "-").replace(".", "-")
        if normalized in pins:
            raise AssertionError(f"Duplicate dependency pin: {name}")
        pins[normalized] = version
    return pins


class DependencyReproducibilityTests(unittest.TestCase):
    def test_complete_requirements_graph_is_exactly_pinned(self) -> None:
        pins = _pinned_requirements()
        self.assertEqual(pins["fastapi"], "0.133.1")
        self.assertEqual(pins["starlette"], "1.0.1")
        self.assertEqual(pins["httpx"], "0.28.1")
        self.assertEqual(
            set(pins),
            {
                "annotated-doc",
                "annotated-types",
                "anyio",
                "certifi",
                "charset-normalizer",
                "click",
                "fastapi",
                "h11",
                "httpcore",
                "httpx",
                "idna",
                "jinja2",
                "markupsafe",
                "pillow",
                "pydantic",
                "pydantic-core",
                "python-dotenv",
                "python-multipart",
                "reportlab",
                "starlette",
                "typing-inspection",
                "typing-extensions",
                "uvicorn",
            },
        )

    def test_running_environment_matches_every_committed_pin(self) -> None:
        mismatches = {
            name: (version, metadata.version(name))
            for name, version in _pinned_requirements().items()
            if metadata.version(name) != version
        }
        self.assertEqual(mismatches, {})

    def test_local_and_windows_setup_use_the_canonical_requirements(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        batch = (ROOT / "start_windows.bat").read_text(encoding="utf-8")
        powershell = (ROOT / "start_windows.ps1").read_text(encoding="utf-8")
        self.assertIn("pip install -r backend/requirements.txt", readme)
        self.assertIn('pip install -r "backend\\requirements.txt"', batch)
        self.assertIn('pip install -r "backend\\requirements.txt"', powershell)

    def test_release_package_contains_the_canonical_requirements(self) -> None:
        with TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "FedorinovRewards_WebPreview"
            package_root.mkdir()
            with patch.object(build_windows_preview_package, "PACKAGE_ROOT", package_root):
                build_windows_preview_package._copy_required_files()
            packaged = package_root / "backend" / "requirements.txt"
            self.assertEqual(packaged.read_bytes(), REQUIREMENTS.read_bytes())


if __name__ == "__main__":
    unittest.main()
