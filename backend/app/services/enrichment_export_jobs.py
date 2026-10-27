"""Read-only export preparation with measured row progress and reconnect status."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
import re
import threading
import time
from . import biography_enrichment as bio


class ExportJobs:
    def __init__(self):
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='enrichment-export')
        self.futures = {}

    def _key(self, settings, operation):
        if not re.fullmatch(r'[a-f0-9]{64}', operation):
            raise bio.ValidationError('Подготовка файла не найдена.')
        return bio._sign(settings, 'export-job-v1:' + operation)

    def _path(self, settings, key):
        return bio._state(settings) / ('export-' + key + '.xlsx')

    def status(self, settings, operation):
        key = self._key(settings, operation)
        with self.lock:
            try:
                item = bio.load_preview(settings, key)
            except bio.ValidationError:
                return {'state': 'unknown', 'operation': operation, 'error': 'Подготовка файла не найдена. Можно начать новую выгрузку.'}
            if item['state'] in {'queued', 'running'} and (key not in self.futures or self.futures[key].done()):
                item.update(state='interrupted', error='Подготовка прервана. Начните новую выгрузку.')
                bio._save(settings, key, item)
            if item['state'] == 'succeeded' and not self._path(settings, key).is_file():
                item.update(state='interrupted', error='Файл больше недоступен. Начните новую выгрузку.')
            return {k: v for k, v in item.items() if k not in {'created', 'sha256'}}

    def start(self, settings, operation, selection, limit):
        bio._selection(selection)
        if not 1 <= limit <= bio.MAX_ROWS:
            raise bio.ValidationError(f'Количество записей: от 1 до {bio.MAX_ROWS}.')
        key = self._key(settings, operation)
        with self.lock:
            try:
                existing = bio.load_preview(settings, key)
            except bio.ValidationError:
                existing = None
            if existing:
                if (existing['selection'], existing['limit']) != (selection, limit):
                    raise bio.ValidationError('Параметры уже начатой выгрузки изменились. Начните новую выгрузку.')
                return self.status(settings, operation)
            item = dict(created=time.time(), operation=operation, state='queued', phase='Выбираем записи…',
                        done=0, total=None, percent=None, selection=selection, limit=limit)
            bio._save(settings, key, item)
            self.futures[key] = self.pool.submit(self._run, settings, key, item)
            return {k: v for k, v in item.items() if k != 'created'}

    def _run(self, settings, key, item):
        last_time = 0
        last_phase = None
        def progress(phase, done, total):
            nonlocal last_time, last_phase
            with self.lock:
                percent = min(99, round(done / total * 100, 1)) if total and phase == 'Подготавливаем записи…' else None
                item.update(state='running', phase=phase, done=done, total=total, percent=percent)
                now = time.monotonic()
                if phase != last_phase or done <= 1 or done == total or now - last_time >= .1:
                    bio._save(settings, key, item)
                    last_time, last_phase = now, phase
        path = self._path(settings, key)
        try:
            content = bio.export_workbook(settings, item['selection'], item['limit'], progress)
            temporary = path.with_suffix('.tmp')
            try:
                temporary.write_bytes(content)
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
            with self.lock:
                item.update(state='succeeded', phase='Файл готов к скачиванию', percent=100,
                            bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception('Export preparation failed')
            with self.lock:
                item.update(state='failed', error=str(exc) if isinstance(exc, bio.ValidationError) else 'Не удалось подготовить файл. Повторите выгрузку.')
        finally:
            with self.lock:
                bio._save(settings, key, item)

    def download(self, settings, operation):
        key = self._key(settings, operation)
        with self.lock:
            status = self.status(settings, operation)
            if status['state'] != 'succeeded':
                raise bio.ValidationError('Файл ещё не готов или больше недоступен. Проверьте состояние выгрузки.')
            item = bio.load_preview(settings, key)
            content = self._path(settings, key).read_bytes()
            if hashlib.sha256(content).hexdigest() != item['sha256']:
                raise bio.ValidationError('Не удалось проверить подготовленный файл. Начните новую выгрузку.')
            return content


jobs = ExportJobs()
