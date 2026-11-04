"""Audited Cyrillic name standardization. No transliteration or schema changes."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import threading
import time
import unicodedata

from ..db import open_readonly_connection, open_write_connection
from . import biography_enrichment as bio, manual_import_review as manual
from .data_operation_lock import exclusive
from .write_guard import ensure_write_allowed

PAIRS=dict(zip('ABCEHKMOPTXYacekopxy','АВСЕНКМОРТХУасекорху'))
TRANSLATION=str.maketrans(PAIRS)
NAME_COLUMNS=('fio','фио','last_name','surname','lastname','family_name','first_name','firstname','patronymic','middle_name','otchestvo','fam','imya','фамилия','имя','отчество')
PREFIX='fio_correction:'


def _name_case(value):
    """Cyrillic components; punctuation/spacing/combining marks stay byte-for-byte.

    Dots terminate single-letter initials only. Apostrophes and supported hyphens
    start a new component. Unbalanced/nested/empty parentheses and other scripts
    or separators need manual review, never an inferred name repair.
    """
    result=[];word=[];depth=0;parenthesis_letters=0;first=True
    hyphens="-‐‑";apostrophes="'’ʼ"
    for index,char in enumerate(value):
        if char in hyphens+apostrophes:
            if index==0 or index+1==len(value) or not (value[index-1].isalpha() or unicodedata.category(value[index-1]).startswith('M')) or not value[index+1].isalpha():
                return value,'Неоднозначный дефис или апостроф в ФИО.'
        elif char.isalpha():
            if 'CYRILLIC' not in unicodedata.name(char,''):
                return value,'Неподдерживаемый алфавит в ФИО.'
            converted=char.upper() if first else char.lower()
            if len(converted)!=1:return value,'Неоднозначное преобразование Unicode-регистра.'
            result.append(converted);word.append(char);first=False
            if depth:parenthesis_letters+=1
            continue
        elif unicodedata.category(char).startswith('M'):
            if first:return value,'Знак ударения или диакритика без буквы.'
            result.append(char);continue
        elif char=='.':
            if len(word)!=1:return value,'Неоднозначное сокращение с точкой; проверьте ФИО вручную.'
        elif char=='(':
            if depth:return value,'Вложенные скобки в ФИО требуют проверки.'
            depth=1;parenthesis_letters=0
        elif char==')':
            if not depth or not parenthesis_letters:return value,'Несогласованные или пустые скобки в ФИО.'
            depth=0
        elif not (char==' ' or unicodedata.category(char)=='Zs'):
            return value,'Нестандартный символ или разделитель в ФИО.'
        result.append(char);word=[];first=True
    if depth:return value,'Незакрытая скобка в ФИО.'
    return ''.join(result),None


def classify(values):
    strings=[v for v in values.values() if isinstance(v,str)]
    latin=[c for v in strings for c in v if 'LATIN' in unicodedata.name(c,'')]
    cyrillic=any('CYRILLIC' in unicodedata.name(c,'') for v in strings for c in v)
    if any(v is not None and not isinstance(v,str) for v in values.values()):
        reason='Поле ФИО содержит нетекстовое значение; требуется ручная проверка.'
    elif not latin and not cyrillic:
        if not any(c.isalpha() for v in strings for c in v):return None
        reason='Неподдерживаемый алфавит в ФИО.'
    elif latin and not cyrillic:reason='Полностью латинское ФИО: нет кириллического контекста.'
    elif any(c not in PAIRS for c in latin):
        reason='Неподдерживаемые латинские символы: '+', '.join(sorted(set(c for c in latin if c not in PAIRS)))
    else:reason=None
    translated={k:v.translate(TRANSLATION) if isinstance(v,str) else v for k,v in values.items()}
    after={};case_change=False
    if reason is None:
        for name,value in translated.items():
            proposed,problem=_name_case(value) if isinstance(value,str) and value.strip() else (value,None)
            if problem:reason=problem;break
            after[name]=proposed;case_change=case_change or proposed!=value
    safe=reason is None
    if safe and after==values:return None
    causes=(['Латинские двойники'] if safe and latin else [])+(['Регистр букв'] if safe and case_change else [])
    return {'before':values,'after':after if safe else dict(values),'safe':safe,'has_latin':bool(latin),
            'homoglyph_change':safe and bool(latin),'case_change':safe and case_change,'reasons':causes,
            'characters':sum(sum(a!=b for a,b in zip(values[k],v)) for k,v in after.items() if isinstance(v,str)) if safe else 0,
            'reason':'; '.join(causes)+'.' if safe else reason}


def columns(connection):
    names={r['name'] for r in connection.execute('pragma table_info(person)')}
    actual={n.casefold():n for n in names}
    fields=[actual[n] for n in NAME_COLUMNS if n in actual]
    if not fields and 'name' in names:fields=['name']
    if not fields or 'id' not in names:raise bio.ValidationError('В схеме не найдены поля ФИО/ID. Схема не изменена.')
    return fields


def scan(connection, progress=lambda *args:None, collect=True):
    fields=columns(connection)
    quoted=','.join('"'+n.replace('"','""')+'"' for n in fields)
    total=connection.execute('select count(*) from person').fetchone()[0]
    digest=hashlib.sha256(bio.canonical(fields).encode());results=[];done=0
    progress('Проверка ФИО',0,total)
    cursor=connection.execute('select id,'+quoted+' from person order by id')
    while True:
        batch=cursor.fetchmany(256)
        if not batch:break
        for row in batch:
            values={n:row[n] for n in fields}
            digest.update(bio.canonical([row['id'],values]).encode())
            if collect:
                candidate=classify(values)
                if candidate:results.append({'id':row['id'],**candidate})
        done+=len(batch);progress('Проверка ФИО',done,total)
    return {'columns':fields,'digest':digest.hexdigest(),'checked':done,'rows':results,
        'latin_records':sum(r['has_latin'] for r in results),
        'homoglyph_records':sum(r['homoglyph_change'] for r in results),'case_records':sum(r['case_change'] for r in results),
        'both_records':sum(r['homoglyph_change'] and r['case_change'] for r in results),'safe_records':sum(r['safe'] for r in results),
        'characters':sum(r['characters'] for r in results),'skipped':sum(not r['safe'] for r in results)}


def _sign(settings,plan):return bio._sign(settings,'fio-audit-v1:'+bio.canonical(plan))


def audit(settings,progress=lambda *args:None):
    with closing(open_readonly_connection(settings.rewards_db_path)) as connection:
        connection.execute('begin');result=scan(connection,progress)
    token=secrets.token_hex(32)
    plan={'created':time.time(),'state':'fio_audit','policy':'fio-standardization-v2','database':str(settings.rewards_db_path.resolve()),**result}
    plan['signature']=_sign(settings,plan);bio._save(settings,token,plan)
    return {'audit_token':token,**{k:plan[k] for k in ['checked','latin_records','homoglyph_records','case_records','both_records','safe_records','characters','skipped']}}


def load_audit(settings,token):
    plan=bio.load_preview(settings,token);unsigned=dict(plan);mac=unsigned.pop('signature','')
    if plan.get('state')!='fio_audit' or plan.get('database')!=str(settings.rewards_db_path.resolve()) or not hmac.compare_digest(mac,_sign(settings,unsigned)):
        raise bio.ValidationError('Предпросмотр исправления повреждён. Повторите аудит.')
    if plan.get('policy')!='fio-standardization-v2':raise bio.ValidationError('Правила стандартизации обновлены. Повторите аудит перед исправлением.')
    return plan


def verified_backup(settings,operation,progress):
    folder=settings.update_backup_dir/'fio-corrections';folder.mkdir(parents=True,exist_ok=True)
    target=folder/('before-'+operation+'.sqlite')
    if target.exists():raise bio.ValidationError('Резервная копия этой операции уже существует. Повторите аудит перед новой попыткой.')
    with closing(open_readonly_connection(settings.rewards_db_path)) as source:
        source.execute('begin')
        schema=source.execute('select type,name,tbl_name,sql from sqlite_master order by type,name').fetchall()
        with closing(sqlite3.connect(target)) as backup:
            source.backup(backup,pages=128,progress=lambda status,remaining,total:progress('Резервная копия',total-remaining,total))
            progress('Проверка резервной копии',0,0)
            if backup.execute('pragma integrity_check').fetchall()!=[('ok',)]:raise bio.ValidationError('Резервная копия не прошла проверку. Запись отменена.')
            copied=backup.execute('select type,name,tbl_name,sql from sqlite_master order by type,name').fetchall()
            if [tuple(r) for r in schema]!=copied:raise bio.ValidationError('Схема резервной копии не совпала. Запись отменена.')
            for row in source.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'"):
                table='"'+row[0].replace('"','""')+'"'
                if source.execute('select count(*) from '+table).fetchone()[0]!=backup.execute('select count(*) from '+table).fetchone()[0]:
                    raise bio.ValidationError('Содержимое резервной копии не совпало. Запись отменена.')
    return {'path':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'integrity':'ok'}


def _receipt(settings,operation):
    with closing(open_readonly_connection(settings.rewards_db_path)) as c:
        manual._audit_available(c)
        row=c.execute('select comment from logs where action=?',(PREFIX+operation,)).fetchone()
        return json.loads(row[0]) if row else None


def apply(settings,token,operation,progress=lambda *args:None):
    ensure_write_allowed(settings)
    if not re.fullmatch('[a-f0-9]{64}',operation):raise bio.ValidationError('Неверный номер операции.')
    with exclusive(settings):
        old=_receipt(settings,operation)
        if old:
            if old['audit_token']!=token:raise bio.ValidationError('Операция относится к другому аудиту.')
            return old
        plan=load_audit(settings,token)
        if not plan['safe_records']:raise bio.ValidationError('Безопасных замен нет. Повторная запись не требуется.')
        with closing(open_readonly_connection(settings.rewards_db_path)) as c:
            c.execute('begin')
            if scan(c,progress,False)['digest']!=plan['digest']:raise bio.ValidationError('ФИО или состав записей изменились. Повторите аудит; ничего не записано.')
        try:backup=verified_backup(settings,operation,progress)
        except (OSError,sqlite3.Error) as exc:raise bio.ValidationError('Не удалось создать проверенную резервную копию. Запись не выполнялась.') from exc
        safe=[r for r in plan['rows'] if r['safe']]
        with closing(open_write_connection(settings.rewards_db_path,settings.write_mode)) as c:
            c.execute('begin immediate')
            try:
                manual._audit_available(c)
                if scan(c,progress,False)['digest']!=plan['digest']:raise bio.ValidationError('Данные изменились во время подготовки. Повторите аудит; запись отменена.')
                progress('Исправление ФИО',0,len(safe))
                for n,row in enumerate(safe,1):
                    names=[name for name in plan['columns'] if row['before'][name]!=row['after'][name]]
                    query=','.join('"'+name.replace('"','""')+'"=?' for name in names)
                    if c.execute('update person set '+query+' where id=?',[row['after'][name] for name in names]+[row['id']]).rowcount!=1:
                        raise bio.ValidationError('Запись не найдена. Все изменения отменены.')
                    stored=c.execute('select '+','.join('\"'+name+'\"' for name in plan['columns'])+' from person where id=?',(row['id'],)).fetchone()
                    if dict(stored)!=row['after']:raise bio.ValidationError('База не сохранила показанные значения. Все изменения отменены.')
                    if n%128==0 or n==len(safe):progress('Исправление ФИО',n,len(safe))
                progress('Сохранение и журнал',0,0)
                event={'time':datetime.now(timezone.utc).isoformat(),'actor':'Пользователь приложения','audit_token':token,
                    'operation':operation,'records':len(safe),'characters':plan['characters'],'backup':backup,'changes':safe,
                    'homoglyph_records':plan['homoglyph_records'],'case_records':plan['case_records'],'skipped':plan['skipped']}
                c.execute('insert into logs(datetime,action,comment) values(?,?,?)',(event['time'],PREFIX+operation,bio.canonical(event)))
                c.commit()
            except BaseException:c.rollback();raise
        return event


def apply_summary(event):
    result={k:event[k] for k in ['records','characters','backup']}
    result.update(homoglyph_records=event.get('homoglyph_records',event['records']),case_records=event.get('case_records',0))
    if 'skipped' in event:result['skipped']=event['skipped']
    return result


class CorrectionJobs:
    def __init__(self):
        self.lock=threading.RLock();self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='fio-correction');self.active={};self.futures={}

    def start(self,settings,kind,request_id,audit_token=None):
        if kind not in {'audit','apply'} or not re.fullmatch('[a-zA-Z0-9-]{16,64}',request_id):raise bio.ValidationError('Неверный запрос.')
        if kind=='apply':ensure_write_allowed(settings)
        job=bio._sign(settings,'fio-job-v1:'+kind+':'+request_id);database=str(settings.rewards_db_path.resolve())
        with self.lock:
            try:old=bio.load_preview(settings,job)
            except bio.ValidationError:old=None
            if old:
                if old.get('kind')!=kind or old.get('audit_token')!=audit_token:raise bio.ValidationError('Номер запроса уже использован.')
                return self.status(settings,job)
            if database in self.active:raise bio.ValidationError('Дождитесь завершения текущей проверки или исправления.')
            if kind=='apply':load_audit(settings,audit_token)
            item={'created':time.time(),'state':'queued','kind':kind,'audit_token':audit_token,'phase':'Подготовка','done':0,'total':0,'percent':0,'eta':None,'job_id':job}
            bio._save(settings,job,item);self.active[database]=job
            self.futures[job]=self.pool.submit(self._run,settings,job,item,database)
            return self.public(item)

    @staticmethod
    def public(item):return {k:v for k,v in item.items() if k not in {'created','audit_token'}}

    def status(self,settings,job):
        with self.lock:
            item=bio.load_preview(settings,job)
            if 'kind' not in item or 'job_id' not in item:raise bio.ValidationError('Операция не найдена.')
            if item['state'] in {'queued','running'} and (job not in self.futures or self.futures[job].done()):
                receipt=_receipt(settings,job) if item['kind']=='apply' else None
                if receipt:item.update(state='succeeded',percent=100,result=apply_summary(receipt))
                else:item.update(state='interrupted',error='Операция была прервана. Успех не подтверждён; выполните новый аудит.',percent=min(99,item['percent']))
                bio._save(settings,job,item)
            return self.public(item)

    def _run(self,settings,job,item,database):
        phase_started=time.monotonic();phase=None
        def progress(label,done,total):
            nonlocal phase_started,phase
            now=time.monotonic()
            if phase!=label:phase=label;phase_started=now
            elapsed=now-phase_started
            with self.lock:
                item.update(state='running',phase=label,done=done,total=total,
                    percent=min(99,round(done/total*100,1)) if total else 0,
                    eta=round(elapsed*(total-done)/done,1) if done and total and elapsed>0 else None,
                    elapsed=round(now-item['_started'],2))
                # No artificial delays. Updates reflect processed batches/pages/rows.
                bio._save(settings,job,{k:v for k,v in item.items() if not k.startswith('_')})
        with self.lock:item['_started']=time.monotonic()
        try:
            if item['kind']=='audit':
                with exclusive(settings):result=audit(settings,progress)
            else:
                event=apply(settings,item['audit_token'],job,progress)
                result=apply_summary(event)
            with self.lock:item.update(state='succeeded',percent=100,phase='Завершено',eta=0,done=result.get('checked',result.get('records',0)),total=result.get('checked',result.get('records',0)),result=result)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception('FIO operation failed')
            with self.lock:item.update(state='failed',percent=min(99,item.get('percent',0)),error=str(exc),eta=None)
        finally:
            with self.lock:
                item.pop('_started',None)
                try:bio._save(settings,job,item)
                finally:self.active.pop(database,None)


jobs=CorrectionJobs()
