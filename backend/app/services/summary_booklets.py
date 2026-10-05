"""Temporary, single-runtime jobs over an immutable matrix membership snapshot."""
from dataclasses import dataclass, field
import logging
from pathlib import Path
import secrets
from tempfile import TemporaryDirectory
from threading import Lock, Thread
import time

from ..config import Settings
from ..repositories.legacy_rewards import person_name_sort_key
from .booklets import generate_person_booklet_pdf

logger = logging.getLogger(__name__)
TTL = 3600


class SummaryBookletError(ValueError):
    pass


@dataclass
class Job:
    id: str
    database: str
    person_ids: tuple[int, ...]
    state: str = "running"
    completed: int = 0
    error: str = ""
    touched: float = field(default_factory=time.monotonic)
    directory: TemporaryDirectory | None = None
    path: Path | None = None

    def status(self):
        total = len(self.person_ids)
        percent = 100 if self.state == "ready" else min(99, self.completed * 100 // total)
        return dict(id=self.id, state=self.state, completed=self.completed, total=total,
                    percent=percent, error=self.error)


class SummaryBookletJobs:
    def __init__(self):
        self.lock = Lock()
        self.snapshots = {}
        self.jobs = {}

    @staticmethod
    def database(settings):
        return str(settings.rewards_db_path.resolve())

    def _cleanup(self):
        threshold = time.monotonic() - TTL
        for token, (_, _, created) in list(self.snapshots.items()):
            if created < threshold:
                del self.snapshots[token]
        for token, job in list(self.jobs.items()):
            if job.state != "running" and job.touched < threshold:
                if job.directory:
                    job.directory.cleanup()
                del self.jobs[token]

    def snapshot(self, settings, rows):
        ordered = sorted(rows, key=lambda row: (person_name_sort_key(row.get("fio")), int(row["id"])))
        ids = tuple(dict.fromkeys(int(row["id"]) for row in ordered))
        with self.lock:
            self._cleanup()
            # Bound abandoned page snapshots without discarding an active job.
            while len(self.snapshots) >= 256:
                del self.snapshots[next(iter(self.snapshots))]
            token = secrets.token_hex(16)
            self.snapshots[token] = (self.database(settings), ids, time.monotonic())
            return token

    def active(self, settings):
        with self.lock:
            return next((job.status() for job in self.jobs.values()
                         if job.database == self.database(settings) and job.state == "running"), None)

    def start(self, settings: Settings, snapshot: str):
        with self.lock:
            self._cleanup()
            database = self.database(settings)
            for job in self.jobs.values():
                if job.database == database and job.state == "running":
                    return job.status()  # A second tab/reload joins the existing operation.
            saved = self.snapshots.get(snapshot)
            if not saved or saved[0] != database:
                raise SummaryBookletError("Результат устарел. Нажмите «Показать» и повторите формирование.")
            if not saved[1]:
                raise SummaryBookletError("В текущем результате нет кавалеров.")
            job = Job(secrets.token_hex(16), database, saved[1])
            self.jobs[job.id] = job
            try:
                Thread(target=self._run, args=(settings, job), daemon=True).start()
            except Exception:
                del self.jobs[job.id]
                raise SummaryBookletError("Не удалось начать формирование. Повторите попытку.")
            return job.status()

    def _run(self, settings, job):
        directory = None
        try:
            from pypdf import PdfWriter
            directory = TemporaryDirectory(prefix="rewards-booklets-")
            root = Path(directory.name)
            with PdfWriter() as writer:
                for person_id in job.person_ids:
                    # Keep the accepted ordinary booklet renderer and all its media rules intact.
                    part = root / f"{person_id}.pdf"
                    generate_person_booklet_pdf(settings, person_id, output_path=part)
                    writer.append(str(part), import_outline=False)
                    part.unlink()
                    with self.lock:
                        job.completed += 1
                output = root / "summary_booklets.pdf"
                writer.add_metadata({"/Title": "Буклеты кавалеров"})
                writer.write(str(output))
            with self.lock:
                job.directory, job.path = directory, output
                job.state, job.touched = "ready", time.monotonic()
        except Exception:
            logger.exception("Summary booklet generation failed: %s", job.id)
            if directory:
                try:
                    directory.cleanup()
                except OSError:
                    logger.exception("Could not remove temporary booklet files: %s", job.id)
            with self.lock:
                job.state = "failed"
                job.error = "Не удалось сформировать буклеты. Повторите попытку. Если ошибка повторяется, обратитесь за помощью."
                job.touched = time.monotonic()

    def _get(self, settings, token):
        self._cleanup()
        job = self.jobs.get(token)
        if not job or job.database != self.database(settings):
            raise SummaryBookletError("Формирование больше недоступно. Нажмите «Показать» и повторите попытку.")
        job.touched = time.monotonic()
        return job

    def status(self, settings, token):
        with self.lock:
            return self._get(settings, token).status()

    def content(self, settings, token):
        with self.lock:
            job = self._get(settings, token)
            if job.state != "ready" or job.path is None:
                raise SummaryBookletError("PDF ещё не готов. Дождитесь завершения формирования.")
            return job.path.read_bytes()


summary_booklet_jobs = SummaryBookletJobs()
