"""Matrix PDF jobs share the accepted booklet lifecycle and unchanged card renderer."""
from dataclasses import asdict
import secrets
import time
from pathlib import Path

from ..config import Settings
from ..repositories.summary import SummaryFilters, summary_matrix, SUMMARY_MATRIX_PHOTO_COLUMNS, SUMMARY_MATRIX_REWARD_PHOTO_COLUMNS, SUMMARY_PDF_REWARD_PHOTO_FIELDS
from .summary_booklets import Job, SummaryBookletError, SummaryBookletJobs
from .summary_pdf import _build_summary_cards_pdf, normalize_summary_pdf_media_fields, normalize_summary_pdf_sort, normalize_summary_pdf_orientation


class SummaryPDFJobs(SummaryBookletJobs):
    filename = 'summary_matrix.pdf'
    failure_message = 'Не удалось сформировать PDF. Повторите попытку. Если ошибка повторяется, обратитесь за помощью.'

    def prepare(self, settings, filters, media_columns='', include_reward_number=False, pdf_sort='fio', pdf_orientation='portrait'):
        matrix = summary_matrix(settings.rewards_db_path, filters)
        if not matrix['rows']:
            raise SummaryBookletError('В текущем результате нет кавалеров.')
        payload = dict(matrix=matrix, filters=asdict(filters), media_columns=normalize_summary_pdf_media_fields(media_columns),
            include_reward_number=str(include_reward_number or '').lower() in {'true','1','on','yes'},
            sort_by=normalize_summary_pdf_sort(pdf_sort), orientation=normalize_summary_pdf_orientation(pdf_orientation))
        with self.lock:
            self._cleanup()
            while len(self.snapshots) >= 256:
                del self.snapshots[next(iter(self.snapshots))]
            token = secrets.token_hex(16)
            self.snapshots[token] = (self.database(settings), payload, time.monotonic())
        return self.start(settings, token)

    def _new_job(self, database, payload):
        return Job(secrets.token_hex(16), database, tuple(row['id'] for row in payload['matrix']['rows']), payload=payload)

    def _worker(self):
        return _generate_matrix_pdf

    def _worker_args(self, settings, job, directory, send):
        return settings.model_dump(), job.payload, directory, send, job.pause_requested


def _generate_matrix_pdf(settings_values, payload, directory, connection, pause_requested):
    completed = 0

    def checkpoint():
        if pause_requested.is_set():
            connection.send(('paused', completed))
            while pause_requested.is_set():
                time.sleep(.05)

    def progress(value):
        nonlocal completed
        completed = value
        connection.send(('progress', completed))

    try:
        labels = dict((*SUMMARY_MATRIX_PHOTO_COLUMNS, *SUMMARY_MATRIX_REWARD_PHOTO_COLUMNS))
        labels.update({field: label for field, (_source, label) in SUMMARY_PDF_REWARD_PHOTO_FIELDS.items()})
        columns = [(field, labels[field]) for field in payload['media_columns']]
        result = _build_summary_cards_pdf(Settings(**settings_values), SummaryFilters(**payload['filters']), payload['matrix'], columns,
            include_reward_number=payload['include_reward_number'], sort_by=payload['sort_by'], orientation=payload['orientation'],
            checkpoint=checkpoint, completed=progress)
        (Path(directory) / 'summary_matrix.pdf').write_bytes(result.content)
        connection.send(('ready', completed))
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Summary PDF generation failed')
        connection.send(('failed', completed))
    finally:
        connection.close()


summary_pdf_jobs = SummaryPDFJobs()
