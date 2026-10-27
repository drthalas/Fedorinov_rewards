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
