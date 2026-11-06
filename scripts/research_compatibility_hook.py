"""Worker adapter. Call before research starts and before owner delivery."""
import hashlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory


def _run_gate(run_root, config, stage, final=None, expected_sha=None):
    root = Path(run_root)
    reports = root / 'state' / 'import-compatibility'
    try:
        target = config['import_compatibility']
        python, checker = (Path(target[key]) for key in ('python', 'checker'))
        if not all(path.is_absolute() and path.is_file() for path in (python, checker)):
            raise ValueError('Нет исполняемого проверяющего целевой версии.')
        reports.mkdir(mode=0o700, parents=True, exist_ok=True)
        original = root / 'input.original.xlsx'
        with TemporaryDirectory(dir=reports) as attempt:
            report = Path(attempt) / 'report.json'
            args = [str(python), str(checker), stage, '--target-sha', target['sha'],
                    '--original', str(original), '--report', str(report)]
            if stage == 'preflight':
                pilot = root / 'input.compatibility-pilot.xlsx'
                args += ['--pilot', str(pilot)]
            if stage == 'final':
                args += ['--xlsx', str(final), '--preflight-report', str(reports / 'preflight.json')]
            process = subprocess.run(args, capture_output=True, text=True, timeout=180)
            verdict = json.loads(report.read_text(encoding='utf-8'))
            report.replace(reports / (stage + '.json'))
        expected = 'PREFLIGHT_PASS' if stage == 'preflight' else 'OFFLINE_COMPATIBLE'
        if process.returncode or verdict['status'] != expected:
            raise ValueError(verdict.get('reason') or ', '.join(verdict.get('blockers', [])) or 'Проверка не пройдена.')
        if verdict.get('target', {}).get('sha') != target['sha']:
            raise ValueError('SHA отчёта отличается от целевого импортёра.')
        if verdict['original_sha256'] != hashlib.sha256(original.read_bytes()).hexdigest():
            raise ValueError('Исходный XLSX изменился.')
        if stage == 'final' and not (verdict['file_sha256'] == expected_sha
                                     == hashlib.sha256(Path(final).read_bytes()).hexdigest()):
            raise ValueError('Файл выдачи отличается от проверенного.')
    except (KeyError, TypeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f'SECURITY: import compatibility {stage} blocked: {exc}') from exc
    return verdict


def require_preflight(run_root, config):
    return _run_gate(run_root, config, 'preflight')


def require_final(run_root, config, final, expected_sha):
    return _run_gate(run_root, config, 'final', final, expected_sha)
