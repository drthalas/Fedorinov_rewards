#!/usr/bin/env python3
"""Fail-closed research preflight and final gate using a pinned product checkout."""
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openpyxl import load_workbook
from backend.app.config import Settings
from backend.app.services import biography_enrichment as bio, enrichment_workflow as workflow
from backend.app.services.enrichment_compatibility import inspect_final, inspect_pilot, original_rows
from backend.app.services import structured_enrichment_evidence as contract
from backend.app.version import APP_VERSION


def target_checkout(expected):
    def git(*args):
        return subprocess.run(['git', '-C', str(ROOT), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    if not re.fullmatch(r'[a-f0-9]{40}', expected) or git('rev-parse', 'HEAD') != expected:
        raise ValueError('Целевой SHA неизвестен или не совпадает с checkout импортёра.')
    if git('status', '--porcelain', '--untracked-files=all', '--', 'backend', 'scripts'):
        raise ValueError('Целевой checkout импортёра содержит локальные изменения.')
    return {'sha': expected, 'version': APP_VERSION}


def fixture_database(root, names):
    path = root / 'preview.sqlite'
    with sqlite3.connect(path) as db:
        db.executescript("""
            create table guide(id integer, name text);
            insert into guide values (1, 'сержант');
            create table person(id integer primary key, fio text, birthday text, id_rank integer, biography text);
            insert into person values (1, 'Иванов Иван Иванович', '1917', 1, null);
            create table rewards(id integer primary key, person_id integer, id_gos integer,
                id_catigory integer, id_sub_catigory integer, id_name integer, number integer, id_link text);
            create table logs(datetime text, action text, comment text);
        """)
        for level, label in enumerate(('СССР', 'Награды', 'Боевые')):
            db.execute(f'create table guide_lev_{level}(id integer, name text)')
            db.execute(f'insert into guide_lev_{level} values (1, ?)', (label,))
        db.execute('create table guide_lev_3(id integer, name text)')
        for index, name in enumerate(names, 1):
            db.execute('insert into guide_lev_3 values (?, ?)', (index, name))
            db.execute('insert into rewards values (?, 1, 1, 1, 1, ?, ?, null)',
                       (index, index, 37 + index))
    return Settings(rewards_db_path=path, rewards_data_dir=root)


def researched_fixture(export, category, case):
    """Synthetic assertions in the real research envelope, attached to TEMP export."""
    source = 'https://warheroes.ru/hero/hero.asp?Hero_id=1'
    exported = original_rows(export)[0][1]
    awards = contract.selected_awards(exported)
    name = awards[0]['award']
    numbers = [str(award['number']) for award in awards]
    path = contract.HSU_A if category == 'hsu' else contract.GLORY_B if case == 'B' else contract.GLORY_A
    serial = '' if case == 'B' else '38'
    fio = 'Иванов Иван Иванович' if case == 'B' else 'Иванов Иван Иоаннович'
    link = {'award': name, 'serial': '38', 'method': 'typed HSU decree', 'ordinal': 1}
    if category == 'glory-i':
        link = {'award': name, 'serial': '38', 'degree': 1, 'date': '24.03.1945', 'paragraph': 1,
                'method': 'order header matched by exact date to typed Glory I decree'}
    if case == 'wrong_degree':
        link['degree'] = 2
    if case == 'wrong_number':
        link['serial'] = '39'
    if case == 'wrong_award':
        link['award'] = 'Орден Трудовой Славы I степени'
    if category == 'hsu':
        ordinal = {'герой советского союза': 1, 'герой советского союза ii': 2, 'герой советского союза iii': 3}
        links = [dict(link, award=award['award'], serial=str(award['number']),
                      ordinal=ordinal[bio.key(award['award'])]) for award in awards]
    else:
        links = [link] if serial else []
    proof = {
        'evidence_version': 2 if case == 'unknown_version' else 1,
        'evidence_category': category, 'state': 'confirmed', 'identity_path': path,
        'source_fio': fio, 'source_url': source, 'profile_sha256': 'a' * 64,
        'source_year': '1917', 'source_year_reliable': True, 'candidate_assessments': [],
        'input_rechecked': {'fio': 'Иванов Иван Иванович', 'year': '1917', 'award': name, 'serials': numbers},
        'source_selected_award_links': links, 'public_award_links': links,
        'all_source_headers': [{'date': '24.03.1945', 'serial': '38', 'label': 'Орден'}],
        'award_proofs': [{'selected_award': name, 'selected_serials': numbers, 'public_links': links,
                          'rank_match': True, 'other_typed_awards': []}],
    }
    payload = json.dumps(proof, ensure_ascii=False)
    notes = {
        'evidence_version': proof['evidence_version'], 'evidence_category': category,
        'research_state': 'confirmed', 'identity_path': path, 'full_evidence_sheet': 'Полные доказательства',
        'full_evidence_ID': '1', 'full_evidence_SHA256': ('0' * 64 if case == 'wrong_digest'
                                                       else hashlib.sha256(payload.encode()).hexdigest()),
        'source_HTML_SHA256': 'a' * 64, 'birth_year_reliable': True,
        'confirmed_GoldStars': [{k: item[k] for k in ('serial', 'ordinal')} for item in links]
                               if category == 'hsu' else [],
        'confirmed_Glory_I': [{k: entry[k] for k in ('award', 'serial', 'degree', 'date', 'method')}
                             for entry in links] if category == 'glory-i' else [],
    }
    with BytesIO() as output:
        workbook = load_workbook(BytesIO(export))
        for column, value in enumerate(('Краткая биография для проверки.', source, 'Найдено'), 5):
            workbook.active.cell(2, column, value)
        proposals = workbook.create_sheet(bio.PROPOSALS_SHEET)
        proposals.append(['ID кавалера', 'ФИО в источнике', 'Год в источнике', 'Награда в источнике',
                          'Номер в источнике', 'Источник', 'Подтверждённые факты', 'Проверка личности', 'Год подтверждён'])
        proposals.append([1, fio, '1917', name, serial, source, json.dumps(notes, ensure_ascii=False),
                          'Личность подтверждена', 'да'])
        evidence = workbook.create_sheet('Полные доказательства')
        evidence.append(['ID кавалера', 'Источник', 'Полные доказательства JSON'])
        evidence.append([1, source, payload])
        workbook.save(output)
        workbook.close()
        return output.getvalue()


def preflight(content):
    selected = set()
    for _, snapshot, _ in original_rows(content):
        awards = contract.selected_awards(snapshot)
        selected.add((contract.category(awards), tuple(snapshot['selection']),
                      tuple(sorted({award['award'] for award in awards}))))
    if any(category == 'unsupported' for category, _, _ in selected):
        raise bio.ValidationError('Выбрана неподдерживаемая категория или степень подписанной награды.')
    cases = []
    for category, selection, names in sorted(selected):
        with TemporaryDirectory(prefix='enrichment-compatibility-') as directory:
            root = Path(directory)
            settings = fixture_database(root, names)
            variants = {'A': {'biography', 'fio'}, 'wrong_digest': set(), 'unknown_version': set()}
            if category == 'glory-i':
                variants.update({'B': {'biography'}, 'wrong_degree': set(),
                                 'wrong_number': set(), 'wrong_award': set()})
            before = settings.rewards_db_path.read_bytes()
            with patch.object(bio, '_state_path', return_value=root / 'private-state'):
                export = bio.export_workbook(settings, '1/1/1')
                for variant, expected in variants.items():
                    candidate = researched_fixture(export, category, variant)
                    token, _ = bio.preview(settings, candidate)
                    view = workflow.workspace(settings, token)
                    actual = {field for field, count in view['totals'].items() if count}
                    cases.append({'category': category, 'selection': selection, 'awards': names, 'case': variant,
                                  'expected': sorted(expected), 'actual': sorted(actual),
                                  'pass': actual == expected and not view['fatal'],
                                  'reasons': [row['reason'] for row in view['rows']]})
            if settings.rewards_db_path.read_bytes() != before:
                raise RuntimeError('TEMP preview изменил базу.')
    return {'status': 'PREFLIGHT_PASS' if cases and all(case['pass'] for case in cases) else 'BLOCKED',
            'original_sha256': hashlib.sha256(content).hexdigest(), 'cases': cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['preflight', 'final'])
    parser.add_argument('--target-sha', required=True)
    parser.add_argument('--original', type=Path, required=True)
    parser.add_argument('--xlsx', type=Path)
    parser.add_argument('--pilot', type=Path)
    parser.add_argument('--preflight-report', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.stage == 'final' and (args.xlsx is None or args.preflight_report is None):
        parser.error('Для final нужны --xlsx и --preflight-report.')
    if args.stage == 'preflight' and args.pilot is None:
        parser.error('Для preflight нужен --pilot от исследовательского экспортёра.')
    if args.report.suffix != '.json' or args.report.exists():
        parser.error('Укажите новый путь отчёта с расширением .json.')
    report = {'status': 'BLOCKED', 'stage': args.stage, 'requested_target': args.target_sha}
    try:
        target = target_checkout(args.target_sha)
        original = args.original.read_bytes()
        if args.stage == 'preflight':
            result = preflight(original)
            result['pilot'] = inspect_pilot(args.pilot.read_bytes(), original)
        else:
            prior = json.loads(args.preflight_report.read_text(encoding='utf-8'))
            if (prior.get('stage') != 'preflight' or prior.get('status') != 'PREFLIGHT_PASS'
                    or prior.get('target') != target
                    or prior.get('original_sha256') != hashlib.sha256(original).hexdigest()):
                raise ValueError('Preflight не пройден для этого входного XLSX и целевого импортёра.')
            candidate = args.xlsx.read_bytes()
            result = inspect_final(candidate, original)
            if args.xlsx.read_bytes() != candidate:
                raise ValueError('Финальный XLSX изменился во время проверки.')
        if args.original.read_bytes() != original:
            raise ValueError('Исходный XLSX изменился во время проверки.')
        report.update(result, target=target)
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        report['reason'] = str(exc)
    with args.report.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(f"{report['status']} {args.report}")
    return 2 if report['status'] == 'BLOCKED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
