#!/usr/bin/env python3
"""Read-only, local diagnosis for 2.0.30+. Does not create/rotate any signing key.

May be copied outside the installation and run with --app-dir and the installed
.venv Python. Only the explicitly chosen JSON report is written. Never upload keys.
"""
import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import re
import sys
import tempfile
from unittest.mock import patch


def code_for(exc):
    if getattr(exc, 'code', None):
        return exc.code, getattr(exc, 'fields', [])
    message = str(exc)
    if 'ключ' in message:
        return 'signing_key_unavailable', []
    if 'устарели' in message:
        fields = message.split('изменены поля: ')[-1].split('. Скачайте')[0].split(', ')
        return 'stale_identity', fields
    for fragment, code in [('Повторяющийся ID','duplicate_id'), ('Изменено исходное поле','protected_field_changed'),
                           ('после проверки','concurrent_fields'), ('журнала logs','audit_unavailable'),
                           ('Истори','receipt_invalid'), ('Подпись','format_mismatch'),
                           ('исходные данные файла','signature_invalid')]:
        if fragment in message:
            return code, []
    return 'guard_unknown', []


def diagnose(settings, content, *, state_root=None):
    from backend.app.services import biography_enrichment as bio, manual_review_choices as choices
    root = state_root or (Path(tempfile.gettempdir()) / 'fedorinov-biography-enrichment' /
                          hashlib.sha256(str(settings.rewards_db_path.resolve()).encode()).hexdigest())
    key_path = root / 'signing.key'
    try:key_modified=datetime.fromtimestamp(key_path.stat().st_mtime,timezone.utc).isoformat()
    except OSError:key_modified=None
    try:
        secret = key_path.read_bytes()
        key_state = 'available' if len(secret) == 32 else 'invalid_length'
    except FileNotFoundError:
        secret, key_state = None, 'missing'
    except OSError:
        secret, key_state = None, 'unreadable'
    # Only reads of this pre-existing private key are allowed, including receipt
    # validation/revision calculation. The production helper would create a key.
    def existing_key(_):
        if key_state != 'available':
            raise bio.ValidationError('Ключ исходной выгрузки недоступен. Диагностика не создаёт новый ключ.')
        return secret
    entries = bio.read_rows(content)
    counts = Counter(e['values'].get('person_id') for e in entries)
    record = {'created': 0, 'state': 'preview', 'file_sha256': hashlib.sha256(content).hexdigest(),
              'entries': entries, 'originals': {}, 'duplicates': [int(k) for k,v in counts.items()
                  if v>1 and re.fullmatch(r'[1-9][0-9]{0,18}', k or '')], 'initial_fields': {}}
    results = []
    with patch.object(bio, '_secret', existing_key), patch.object(bio, '_state', return_value=root), closing(bio._connection(settings.rewards_db_path)) as connection:
        # Same read transaction for both initial classification and every guard.
        record['rows'] = []
        for entry in entries:
            try:row = bio._assess(connection, settings, entry, {}, set(record['duplicates']))
            except (TypeError,KeyError,ValueError):
                row = {'row':entry['row'],'kind':bio.ERROR}
            record['rows'].append(row)
        for entry in entries:
            values = entry['values']; pid = values.get('person_id')
            serialized=values.get('snapshot',''); signature=values.get('snapshot_signature','')
            signature_pass=None if key_state!='available' else bool(serialized and re.fullmatch(r'[a-f0-9]{64}',signature) and hmac.compare_digest(signature,hmac.new(secret,serialized.encode(),hashlib.sha256).hexdigest()))
            item = {'row':entry['row'], 'person_id':pid, 'biography_characters':len(values.get('biography','')),
                    'snapshot_present':bool(serialized),'signature_present':bool(signature),'hmac_valid':signature_pass}
            try:
                review = choices.detail(settings, 'diagnostic-only', entry['row'], connection=connection, record=record)
                item.update(guard_pass=True, state=review['state'], reason=review['reason'], fields=list(review['automatic']))
            except (bio.ValidationError,TypeError,ValueError,KeyError) as exc:
                code, fields = code_for(exc) if isinstance(exc,bio.ValidationError) else ('snapshot_invalid',[])
                # Older2.0.30 combines signature failures in one message. Keep
                # missing data/key and actual HMAC mismatch separate anyway.
                if not serialized:code,fields='snapshot_missing',['snapshot']
                elif not signature:code,fields='signature_missing',['snapshot_signature']
                elif key_state!='available':code,fields='signing_key_unavailable',[]
                elif signature_pass is False:code,fields='signature_invalid',['snapshot_signature']
                item.update(guard_pass=False, code=code, fields=fields, reason=str(exc))
            results.append(item)
    failures = [r for r in results if not r['guard_pass']]
    return {'schema':'enrichment-diagnostic-v1', 'created_utc':datetime.now(timezone.utc).isoformat(),
            'file_sha256':record['file_sha256'], 'file_bytes':len(content), 'rows':len(entries),
            'profile_path_sha256':hashlib.sha256(str(settings.rewards_db_path.resolve()).encode()).hexdigest(),
            'signing_key_state':key_state, 'signing_key_modified_utc':key_modified,
            'installation_path_sha256':hashlib.sha256(str(settings.app_install_dir.resolve()).encode()).hexdigest(),
            'key_value_in_report':False, 'key_created_or_changed':False,
            'database_write':False, 'fatal':bool(failures), 'prepared':sum(r.get('state')=='ready' for r in results),
            'hmac_valid_rows':sum(r['hmac_valid'] is True for r in results),
            'hmac_invalid_rows':sum(r['hmac_valid'] is False for r in results),
            'hmac_not_tested_rows':sum(r['hmac_valid'] is None for r in results),
            'failure_counts':dict(Counter(r['code'] for r in failures)), 'guard_failures':failures, 'results':results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-dir', type=Path, default=Path.cwd())
    parser.add_argument('--xlsx', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.app_dir.resolve()))
    from backend.app.config import get_settings
    from backend.app.version import APP_VERSION
    from backend.app.services import biography_enrichment as bio
    settings = get_settings(); output = args.output.resolve()
    protected = [settings.rewards_db_path.resolve(), args.xlsx.resolve()]
    if output in protected or output.name == 'signing.key' or output.suffix.lower() != '.json':
        parser.error('Укажите новый отдельный JSON-отчёт, не файл данных или ключа.')
    if output.exists():
        parser.error('Отчёт уже существует. Укажите новое имя, чтобы сохранить предыдущий.')
    try:
        result = diagnose(settings, args.xlsx.read_bytes()); result['app_version'] = APP_VERSION
    except (bio.ValidationError, OSError, ValueError) as exc:
        result = {'fatal':True, 'diagnostic_error':str(exc), 'database_write':False, 'key_created_or_changed':False}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:result.get(k) for k in ['app_version','fatal','rows','prepared','signing_key_state','failure_counts','diagnostic_error']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
