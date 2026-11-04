"""Observable import status around the unchanged atomic/idempotent write protocol."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hmac
import threading
import time
from . import biography_enrichment as bio,enrichment_workflow as flow,manual_review_choices as choices
from .write_guard import ensure_write_allowed

class ImportJobs:
    def __init__(self):
        self.lock=threading.RLock();self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='enrichment-import');self.futures={}
    def _key(self,settings,operation):return bio._sign(settings,'import-job-v1:'+operation)
    def status(self,settings,operation):
        # Loading the signed plan verifies this is a valid private operation.
        plan=bio.load_preview(settings,operation);unsigned=dict(plan);mac=unsigned.pop('signature','')
        if plan.get('state')!='file_import_plan' or not hmac.compare_digest(mac,bio._sign(settings,bio.canonical(unsigned))):raise bio.ValidationError('Подтверждение импорта повреждено.')
        receipt=flow.committed_result(settings,operation)
        if receipt:return {'state':'succeeded','operation':operation,'phase':'Импорт завершён','percent':100,'done':len(plan['rows']),'total':len(plan['rows']),'result':flow.result_summary(receipt)}
        key=self._key(settings,operation)
        with self.lock:
            try:item=bio.load_preview(settings,key)
            except bio.ValidationError:return {'state':'unknown','operation':operation,'phase':'Статус не подтверждён','done':0,'total':len(plan['rows']),'percent':0,'error':'Результат операции пока не подтверждён. Обновите статус; запись повторно не запускается.'}
            if item['state']=='succeeded' or item['state'] in {'queued','running'} and (key not in self.futures or self.futures[key].done()):
                receipt=flow.committed_result(settings,operation)
                if receipt:return {'state':'succeeded','operation':operation,'phase':'Импорт завершён','percent':100,'done':len(plan['rows']),'total':len(plan['rows']),'result':flow.result_summary(receipt)}
                item.update(state='interrupted',percent=min(99,item.get('percent',0)),error='Импорт был прерван. Сохранение не подтверждено. Вернитесь к проверке; для новой записи потребуется общее подтверждение.')
                bio._save(settings,key,item)
            return {k:v for k,v in item.items() if k!='created'}
    def start(self,settings,operation):
        ensure_write_allowed(settings)
        with self.lock:
            state=self.status(settings,operation);key=self._key(settings,operation)
            if state['state']!='unknown':return state
            try:existing=bio.load_preview(settings,key)
            except bio.ValidationError:existing=None
            if existing:return self.status(settings,operation)
            item={'created':time.time(),'state':'queued','operation':operation,'phase':'Импортируем данные…','done':0,'total':state['total'],'percent':0}
            bio._save(settings,key,item);self.futures[key]=self.pool.submit(self._run,settings,operation,key,item)
            return {k:v for k,v in item.items() if k!='created'}
    def _run(self,settings,operation,key,item):
        last_persist=0;last_phase=None
        def progress(phase,done,total):
            nonlocal last_persist,last_phase
            with self.lock:
                item.update(state='running',phase=phase,done=done,total=total,percent=min(99,round(done/total*100,1)) if total else 0)
                now=time.monotonic()
                if done<=1 or done==total or phase!=last_phase or now-last_persist>=.1:
                    bio._save(settings,key,item);last_persist=now;last_phase=phase
        try:
            result=flow.commit_import(settings,operation,progress)
            with self.lock:item.update(state='succeeded',phase='Импорт завершён',percent=100,result=flow.result_summary(result))
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception('Import operation failed')
            with self.lock:item.update(state='failed',error=choices.friendly_error(exc),percent=min(99,item.get('percent',0)))
        finally:
            with self.lock:bio._save(settings,key,item)

jobs=ImportJobs()

class PreparationJobs:
    """Read-only preparation on the existing bounded import worker pool.

    A durable request ID survives a lost start response. A workspace slot also
    coalesces distinct double submits while work is active. Restarted workers
    are reported as interrupted, never silently restarted or committed.
    """
    def __init__(self, lifecycle):
        self.lifecycle=lifecycle;self.lock=lifecycle.lock;self.futures={};self.active={}
    def _key(self,settings,value):return bio._sign(settings,'prepare-job-v1:'+value)
    def _save(self,settings,key,item):
        value=dict(item);value['signature']=bio._sign(settings,bio.canonical(value));bio._save(settings,key,value)
    def _load(self,settings,key):
        item=bio.load_preview(settings,key);mac=item.pop('signature','')
        if not hmac.compare_digest(mac,bio._sign(settings,bio.canonical(item))):raise bio.ValidationError('Состояние подготовки повреждено. Повторите проверку файла; ничего не записано.')
        return item
    def _public(self,key,item):
        return {'job':key,**{k:item.get(k) for k in ('state','phase','done','total','percent','error','operation')}}
    def status(self,settings,key):
        with self.lock:
            try:item=self._load(settings,key)
            except (bio.ValidationError,OSError):
                return {'job':key,'state':'unknown','error':'Состояние подготовки недоступно. Данные не записывались. Повторите статус или проверку файла.'}
            if item.get('kind')!='prepare':raise bio.ValidationError('Неверная операция подготовки.')
            if item['state'] in {'queued','running'} and (key not in self.futures or self.futures[key].done()):
                item.update(state='interrupted',percent=None,error='Серверная подготовка прервана. Данные не записывались. Повторите проверку файла.')
                self._save(settings,key,item)
            return self._public(key,item)
    def start(self,settings,token,revision,request_id,render):
        import re
        if not all(re.fullmatch(r'[a-f0-9]{64}',v or '') for v in (token,revision)) or not re.fullmatch(r'[a-f0-9]{32}',request_id or ''):
            raise bio.ValidationError('Неверный запрос подготовки. Вернитесь к списку и повторите проверку.')
        key=self._key(settings,token+':'+revision+':'+request_id)
        workspace=self._key(settings,'workspace:'+token);slot=self._key(settings,'slot:'+token+':'+revision)
        with self.lock:
            try:existing=self._load(settings,key)
            except bio.ValidationError:existing=None
            if existing:return self.status(settings,existing['target'] if existing.get('kind')=='prepare_alias' else key)
            if key in self.futures and not self.futures[key].done():return self.status(settings,key)
            if (bio._state(settings)/(key+'.json')).exists():return self.status(settings,key)
            def coalesce(previous):
                self._save(settings,key,{'created':time.time(),'kind':'prepare_alias','target':previous})
                return self.status(settings,previous)
            for previous in (self.active.get(workspace),):
                if previous and ((previous in self.futures and not self.futures[previous].done()) or self.status(settings,previous)['state'] in {'queued','running'}):return coalesce(previous)
            try:previous=self._load(settings,slot).get('job')
            except bio.ValidationError:previous=None
            if previous and ((previous in self.futures and not self.futures[previous].done()) or self.status(settings,previous)['state'] in {'queued','running'}):return coalesce(previous)
            self.futures={k:f for k,f in self.futures.items() if not f.done()}
            self.active={k:v for k,v in self.active.items() if v in self.futures}
            if len(self.futures)>=2:
                raise bio.ValidationError('Сервер занят подготовкой других файлов. Данные не записывались. Повторите проверку позже.')
            item={'created':time.time(),'kind':'prepare','state':'queued','phase':'Ожидаем начала проверки…',
                  'token':token,'revision':revision,'done':0,'total':None,'percent':None}
            self._save(settings,key,item);self._save(settings,slot,{'created':time.time(),'job':key})
            self.active[workspace]=key
            self.futures[key]=self.lifecycle.pool.submit(self._run,settings,key,item,render)
            return self._public(key,item)
    @staticmethod
    def failure(exc):
        import sqlite3
        if isinstance(exc,sqlite3.Error):
            if any(n in str(exc).lower() for n in ('locked','busy')):return 'База занята другой операцией. Данные не записывались. Дождитесь её окончания и повторите проверку.'
            return 'Не удалось прочитать базу данных. Ничего не записано. Проверьте доступность базы и повторите проверку.'
        if isinstance(exc,bio.ValidationError):return choices.friendly_error(exc)
        if isinstance(exc,OSError):return 'Не удалось прочитать файл или сохранить план проверки. Данные не записывались. Проверьте доступность хранилища и повторите проверку.'
        return 'Сервер не смог завершить подготовку. Данные не записывались. Повторите проверку; при повторении ошибки обратитесь к администратору.'
    def _run(self,settings,key,item,render):
        last=0;last_phase=None;metrics={}
        def progress(phase,done,total):
            nonlocal last,last_phase
            with self.lock:
                item.update(state='running',phase=phase,done=done,total=total,
                    percent=min(99,round(done/total*100,1)) if total else None)
                now=time.monotonic()
                if phase!=last_phase or done in (0,1,total) or now-last>=.15:
                    self._save(settings,key,item);last=now;last_phase=phase
        try:
            started=time.perf_counter()
            operation,plan=flow.prepare_workspace(settings,item['token'],item['revision'],[],progress=progress,metrics=metrics)
            progress('Подготавливаем сводку…',0,None);render_start=time.perf_counter()
            html=render(plan,operation);metrics['render_seconds']=time.perf_counter()-render_start
            self._save(settings,self._key(settings,'result:'+key),{'created':item['created'],'job':key,'html':html,'operation':operation})
            metrics['wall_seconds']=time.perf_counter()-started
            with self.lock:item.update(state='succeeded',phase='Сводка готова',percent=100,operation=operation,metrics=metrics)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception('Read-only import preparation failed')
            with self.lock:item.update(state='failed',percent=None,error=self.failure(exc))
        finally:
            try:
                with self.lock:self._save(settings,key,item)
            except OSError:
                # If storage failed, the next status cannot claim success: a
                # running state without a live worker becomes interrupted.
                import logging
                logging.getLogger(__name__).exception('Cannot persist preparation status')
    def result(self,settings,key):
        with self.lock:
            state=self.status(settings,key)
            if state['state']!='succeeded':raise bio.ValidationError('Сводка ещё недоступна. Проверьте состояние подготовки.')
            result=self._load(settings,self._key(settings,'result:'+key))
            if result.get('job')!=key or result.get('operation')!=state['operation']:
                raise bio.ValidationError('Сводка недоступна. Повторите проверку; ничего не записано.')
            # The cached fragment is authenticated; the existing commit endpoint
            # revalidates signatures, current cards and receipts transactionally.
            return result['html']

preparations=PreparationJobs(jobs)
