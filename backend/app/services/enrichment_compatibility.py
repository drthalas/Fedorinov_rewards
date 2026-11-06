"""Offline compatibility only. Never authenticate a recipient export here."""
from collections import Counter, defaultdict
import hashlib
import re

from . import biography_enrichment as bio
from . import manual_import_review as manual
from . import manual_review_choices as choices
from . import structured_enrichment_evidence as contract


def original_rows(content):
    rows = bio.read_rows(content)
    originals = []
    seen = set()
    for row in rows:
        values = row['values']
        if row['invalid'] or not re.fullmatch(r'[a-f0-9]{64}', values.get('snapshot_signature', '')):
            raise bio.ValidationError(f"Строка {row['row']}: повреждены данные или формат подписи.")
        snapshot = bio.decode_snapshot(values.get('snapshot'))
        original = manual.protected_original(values, snapshot)
        pid = original['person_id']
        if pid in seen:
            raise bio.ValidationError(f'Повторяющийся ID {pid}.')
        seen.add(pid)
        originals.append((values, snapshot, original))
    if not originals:
        raise bio.ValidationError('В XLSX нет подписанных строк.')
    return originals


def inspect_final(content, original_content):
    """Run the production parser and decision logic with snapshot-derived state."""
    rows = original_rows(content)
    input_rows = original_rows(original_content)
    signed_columns = ('snapshot', 'snapshot_signature')
    signed = lambda entries: [tuple(values[key] for key in signed_columns) for values, _, _ in entries]
    if signed(rows) != signed(input_rows):
        raise bio.ValidationError('Порядок, исходные snapshot или подписи отличаются от входного XLSX.')
    return _inspect_rows(rows, content, original_content)


def inspect_pilot(content, original_content):
    """Check a small sample produced by the research exporter itself."""
    rows = original_rows(content)
    input_rows = original_rows(original_content)
    known = {original['person_id']: (values['snapshot'], values['snapshot_signature'])
             for values, _, original in input_rows}
    if any(known.get(original['person_id']) != (values['snapshot'], values['snapshot_signature'])
           for values, _, original in rows):
        raise bio.ValidationError('Пилот содержит строки вне исходной подписанной выгрузки.')
    required = {contract.category(contract.selected_awards(snapshot)) for _, snapshot, _ in input_rows}
    if len(rows) > 10 * len(required):
        raise bio.ValidationError('Пилот должен содержать не более 10 строк на категорию.')
    report = _inspect_rows(rows, content, original_content)
    positive = {row['category'] for row in report['rows'] if 'biography' in row['fields']}
    negative = {row['category'] for row in report['rows'] if not row['fields']}
    if report['status'] != 'OFFLINE_COMPATIBLE' or not required <= positive & negative:
        raise bio.ValidationError('Пилот должен пройти проверку и содержать допущенный BIO и недопущенную строку каждой категории.')
    return {'sha256': report['file_sha256'], 'groups': report['groups']}


def _inspect_rows(rows, content, original_content):
    groups = defaultdict(Counter)
    reasons = Counter()
    items = []
    blockers = set()
    for values, snapshot, original in rows:
        person = snapshot['person']
        current = {'fio': person['fio'], 'birthday': person['birthday'], 'biography': None}
        kind, _ = bio.assess_payload(values, original, person, None)
        review = choices.classify(values, snapshot, current, kind, {}, [])
        typed = review['evidence'] or {}
        category = contract.category(contract.selected_awards(snapshot))
        code = typed.get('code', 'missing_evidence')
        fields = sorted(review['automatic'])
        has_bio = not bio.blank(values.get('biography'))
        path = typed.get('path') or 'review'
        version = typed.get('version')
        counts = groups[(category, version, path)]
        counts.update(rows=1, prepared_bio=int(has_bio), no_bio=int(not has_bio),
                      ready=int(bool(fields)), review=int(review['state'] == 'blocked'))
        counts.update({field: 1 for field in fields})
        if category == 'unsupported' or code in {'unsupported_category', 'unsupported_version'}:
            blockers.add('unsupported_contract')
        if has_bio and code in {'evidence_digest', 'source_digest', 'evidence_envelope', 'source_mismatch', 'missing_evidence'}:
            blockers.add('invalid_evidence')
        if not fields:
            reasons[typed.get('reason') or review['reason']] += 1
        items.append({'id': person['person_id'], 'category': category, 'version': version, 'path': path,
                      'code': code, 'has_bio': has_bio, 'fields': fields, 'reason': review['reason']})
    totals = Counter()
    for counts in groups.values():
        totals.update(counts)
    if not totals['biography']:
        blockers.add('zero_bio_admission')
    if any(counts['prepared_bio'] and 2 * counts['biography'] <= counts['prepared_bio']
           for counts in groups.values()):
        blockers.add('mass_bio_rejection')
    return {
        'status': 'BLOCKED' if blockers else 'OFFLINE_COMPATIBLE',
        'blockers': sorted(blockers),
        'file_sha256': hashlib.sha256(content).hexdigest(),
        'original_sha256': hashlib.sha256(original_content).hexdigest(),
        'hmac': 'not_checked', 'recipient_db': 'not_checked', 'stale': 'not_checked',
        'totals': dict(totals),
        'groups': [{'category': cat, 'version': ver, 'path': path, **counts}
                   for (cat, ver, path), counts in groups.items()],
        'reasons': dict(reasons), 'rows': items,
    }
