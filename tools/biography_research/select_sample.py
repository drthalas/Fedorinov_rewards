"""Read-only, seeded sampling. Run on the source host; stdout is private data."""
import argparse
import hashlib
import json
import random
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def blank(value):
    return value is None or isinstance(value, str) and not value.strip()


def sample(db, seed, count=50):
    db = Path(db).resolve(strict=True)
    before = db.stat()
    sidecars = lambda: [s for s in ('-wal', '-shm', '-journal') if Path(str(db)+s).exists()]
    if sidecars():
        raise ValueError('STOP: active SQLite sidecars; no unsafe recovery permitted')
    with db.open('rb') as handle:
        header = handle.read(100)
    if header[:16] != b'SQLite format 3\0' or header[18:20] != b'\x01\x01':
        raise ValueError('STOP: unsupported WAL/header; source not opened')
    connection = sqlite3.connect(db.as_uri()+'?mode=ro', uri=True, timeout=2)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('PRAGMA query_only=ON')
        connection.execute('BEGIN')
        columns = {r['name'] for r in connection.execute('PRAGMA table_info(person)')}
        if 'biography' not in columns:
            raise ValueError('STOP: person.biography missing')
        connection.create_function('bio_blank', 1, lambda value: int(blank(value)), deterministic=True)
        hierarchy = connection.execute('''SELECT DISTINCT r.id_gos,r.id_catigory,r.id_sub_catigory,r.id_name,
          g0.name country,g1.name category,g2.name subcategory,g3.name award
          FROM rewards r JOIN guide_lev_0 g0 ON g0.id=r.id_gos
          JOIN guide_lev_1 g1 ON g1.id=r.id_catigory
          JOIN guide_lev_2 g2 ON g2.id=r.id_sub_catigory
          JOIN guide_lev_3 g3 ON g3.id=r.id_name
          WHERE g0.name=? AND g1.name=? AND g2.name=? AND g3.name=?''',
          ('СССР','Боевые','Ордена','Александра Невского')).fetchall()
        if len(hierarchy) != 1:
            raise ValueError('STOP: award hierarchy ambiguous or absent')
        hierarchy = dict(hierarchy[0])
        ids = tuple(hierarchy[k] for k in ('id_gos','id_catigory','id_sub_catigory','id_name'))
        pool = [r[0] for r in connection.execute('''SELECT DISTINCT p.id FROM person p
          JOIN rewards r ON r.person_id=p.id WHERE r.id_gos=? AND r.id_catigory=?
          AND r.id_sub_catigory=? AND r.id_name=? AND bio_blank(p.biography)=1 ORDER BY p.id''', ids)]
        if len(pool) < count:
            raise ValueError('STOP: fewer than required eligible persons')
        chosen = random.Random(seed).sample(pool, count)
        rows = []
        for order, person_id in enumerate(chosen, 1):
            person = dict(connection.execute('''SELECT p.id,p.fio,p.birthday,g.name rank,p.link1,p.link2,p.biography
              FROM person p LEFT JOIN guide g ON g.id=p.id_rank WHERE p.id=?''', (person_id,)).fetchone())
            if not blank(person['biography']):
                raise ValueError('STOP: selected biography is not blank')
            rewards = [dict(r) for r in connection.execute('''SELECT r.id_gos,r.id_catigory,r.id_sub_catigory,r.id_name,
              r.number,g0.name country,g1.name category,g2.name subcategory,g3.name award,r.id_link
              FROM rewards r LEFT JOIN guide_lev_0 g0 ON g0.id=r.id_gos
              LEFT JOIN guide_lev_1 g1 ON g1.id=r.id_catigory
              LEFT JOIN guide_lev_2 g2 ON g2.id=r.id_sub_catigory
              LEFT JOIN guide_lev_3 g3 ON g3.id=r.id_name WHERE r.person_id=? ORDER BY r.id''', (person_id,))]
            selected = [r for r in rewards if tuple(r[k] for k in ('id_gos','id_catigory','id_sub_catigory','id_name')) == ids]
            birth = str(person['birthday'] or '')
            match = re.match(r'(\d{4})', birth)
            year = match.group(1) if match else ''
            urls = []
            for field in [person['link1'],person['link2'],*(r['id_link'] for r in rewards)]:
                urls.extend(re.findall(r'https?://[^\s<>"\]]+', str(field or '')))
            numbers = [str(r['number']) for r in selected if r['number'] is not None]
            rows.append({'sample_order':order,'person_id':str(person_id),'ФИО':person['fio'] or '',
              'Год рождения':year,'Звание':person['rank'] or '', 'Награда':hierarchy['award'],
              'Иерархия ID':' / '.join(map(str,ids)), 'Номер(а) награды':' | '.join(numbers),
              'Другие награды':' | '.join(f"{r['award'] or '[Без названия]'} №{'' if r['number'] is None else r['number']}" for r in rewards if r not in selected),
              'Сохранённые URL':'\n'.join(dict.fromkeys(urls)), 'Текущая биография':person['biography'] or '',
              'Примечание к году':'1945: возможный import fallback; требует независимого подтверждения' if year=='1945' else ''})
        if connection.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('STOP: integrity failure')
        after = db.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns) or sidecars():
            raise ValueError('STOP: source changed during selection')
        pool_digest = hashlib.sha256(json.dumps(pool,separators=(',',':')).encode()).hexdigest()
        return {'metadata':{'seed':seed,'algorithm':'random.Random(seed).sample(sorted DISTINCT person.id pool, 50)',
          'pool_count':len(pool),'pool_sha256':pool_digest,'hierarchy':hierarchy,'selected_count':len(rows),
          'unique_ids':len(set(chosen)), 'source_basename':db.name,'source_size':before.st_size,
          'source_mtime_utc':datetime.fromtimestamp(before.st_mtime,timezone.utc).isoformat(),
          'extracted_at_utc':datetime.now(timezone.utc).isoformat(),'mode':'ro/query_only, single read transaction',
          'source_unchanged':True},'rows':rows}
    finally:
        connection.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', required=True)
    parser.add_argument('--seed', required=True, type=int)
    args = parser.parse_args()
    print(json.dumps(sample(args.db,args.seed),ensure_ascii=True))
