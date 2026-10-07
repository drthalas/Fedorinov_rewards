"""Temporary, single-runtime jobs over an immutable matrix membership snapshot."""
from dataclasses import dataclass, field
import logging
import multiprocessing
from pathlib import Path
import secrets
from tempfile import TemporaryDirectory
from threading import Event, Lock, Thread
import time

from ..config import Settings
from ..repositories.legacy_rewards import person_name_sort_key
from .booklets import generate_person_booklet_pdf

logger = logging.getLogger(__name__)
TTL = 3600
ACTIVE_STATES = {"running", "pausing", "paused", "stopping"}


class SummaryBookletError(ValueError):
    pass


@dataclass
class Job:
    id: str
    database: str
    person_ids: tuple[int, ...]
    contents_rows: tuple[dict, ...] = ()
    payload: dict = field(default_factory=dict)
    state: str = "running"
    completed: int = 0
    error: str = ""
    touched: float = field(default_factory=time.monotonic)
    directory: TemporaryDirectory | None = None
    path: Path | None = None
    pause_requested: object = None
    stop_requested: Event = field(default_factory=Event)

    def status(self):
        total = len(self.person_ids)
        percent = 100 if self.state == "ready" else min(99, self.completed * 100 // total)
        return dict(id=self.id, state=self.state, completed=self.completed, total=total,
                    percent=percent, error=self.error)


class SummaryBookletJobs:
    filename = "summary_booklets.pdf"
    failure_message = "Не удалось сформировать буклеты. Повторите попытку. Если ошибка повторяется, обратитесь за помощью."

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
            if job.state not in ACTIVE_STATES and job.touched < threshold:
                if job.directory:
                    job.directory.cleanup()
                del self.jobs[token]

    def snapshot(self, settings, rows):
        ordered = sorted(rows, key=lambda row: (person_name_sort_key(row.get("fio")), int(row["id"])))
        ids = tuple(dict.fromkeys(int(row["id"]) for row in ordered))
        by_id = {int(row["id"]): row for row in ordered}
        contents_rows = tuple(dict(id=ident, fio=by_id[ident].get("fio"),
            birthday=by_id[ident].get("birthday"), rank_name=by_id[ident].get("rank_name"),
            pdf_reward_numbers=tuple(by_id[ident].get("pdf_reward_numbers") or ())) for ident in ids)
        with self.lock:
            self._cleanup()
            # Bound abandoned page snapshots without discarding an active job.
            while len(self.snapshots) >= 256:
                del self.snapshots[next(iter(self.snapshots))]
            token = secrets.token_hex(16)
            self.snapshots[token] = (self.database(settings), contents_rows, time.monotonic())
            return token

    def active(self, settings):
        with self.lock:
            return next((job.status() for job in self.jobs.values()
                         if job.database == self.database(settings) and job.state in ACTIVE_STATES), None)

    def start(self, settings: Settings, snapshot: str):
        with self.lock:
            self._cleanup()
            database = self.database(settings)
            for job in self.jobs.values():
                if job.database == database and job.state in ACTIVE_STATES:
                    return job.status()  # A second tab/reload joins the existing operation.
            saved = self.snapshots.get(snapshot)
            if not saved or saved[0] != database:
                raise SummaryBookletError("Результат устарел. Нажмите «Показать» и повторите формирование.")
            if not saved[1]:
                raise SummaryBookletError("В текущем результате нет кавалеров.")
            job = self._new_job(database, saved[1])
            job.pause_requested = multiprocessing.get_context("spawn").Event()
            self.jobs[job.id] = job
            try:
                Thread(target=self._run, args=(settings, job), daemon=True).start()
            except Exception:
                del self.jobs[job.id]
                raise SummaryBookletError("Не удалось начать формирование. Повторите попытку.")
            return job.status()

    def _new_job(self, database, rows):
        return Job(secrets.token_hex(16), database, tuple(row["id"] for row in rows), rows)

    def _worker(self):
        return _generate_booklets

    def _worker_args(self, settings, job, directory, send):
        return (settings.model_dump(), job.person_ids, directory, send, job.pause_requested, job.contents_rows)

    def control(self, settings, token, action):
        with self.lock:
            job = self._get(settings, token)
            if action == "stop" and job.state in ACTIVE_STATES:
                job.state = "stopping"
                job.stop_requested.set()
            elif action == "pause" and job.state == "running":
                job.state = "pausing"
                job.pause_requested.set()
            elif action == "resume" and job.state in {"paused", "pausing"}:
                job.pause_requested.clear()
                job.state = "running"
            elif action not in {"pause", "resume", "stop"}:
                raise SummaryBookletError("Неизвестное действие.")
            return job.status()

    def _run(self, settings, job):
        directory = None
        process = None
        receive = send = None
        ready = False
        failure = False
        try:
            directory = TemporaryDirectory(prefix="rewards-booklets-")
            context = multiprocessing.get_context("spawn")
            receive, send = context.Pipe(duplex=False)
            process = context.Process(target=self._worker(),
                args=self._worker_args(settings, job, directory.name, send),
                daemon=True)
            process.start()
            send.close()
            with self.lock:
                job.directory = directory
            while not job.stop_requested.is_set():
                if receive.poll(0.1):
                    try:
                        event, completed = receive.recv()
                    except EOFError:
                        break
                    with self.lock:
                        if job.state == "stopping":
                            break
                        job.completed = completed
                        if event == "paused" and job.pause_requested.is_set():
                            job.state = "paused"
                        elif event == "ready":
                            ready = True
                            break
                        elif event == "failed":
                            failure = True
                            break
                elif not process.is_alive():
                    break
            if job.stop_requested.is_set() or not ready:
                if process.is_alive():
                    process.terminate()
            process.join(5)
            if process.is_alive():
                process.kill()
                process.join()
            with self.lock:
                # Stop wins even if it raced with the final ready notification.
                if ready and process.exitcode == 0 and not job.stop_requested.is_set():
                    job.path = Path(directory.name) / self.filename
                    job.state, job.touched = "ready", time.monotonic()
                    directory = None  # Retain only complete artifacts until TTL.
                elif not job.stop_requested.is_set():
                    failure = True
        except Exception:
            logger.exception("Summary booklet worker failed: %s", job.id)
            failure = True
        finally:
            if process is not None and process.is_alive():
                process.terminate()
                process.join()
            for connection in (receive, send):
                if connection is not None:
                    connection.close()
            if directory:
                try:
                    directory.cleanup()
                except OSError:
                    logger.exception("Could not remove temporary booklet files: %s", job.id)
                    failure = True
                with self.lock:
                    job.directory = None
            with self.lock:
                if job.state != "ready":
                    job.path = None
                    job.state = "failed" if failure else "stopped"
                    if failure:
                        job.error = self.failure_message
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


def _generate_booklets(settings_values, person_ids, directory, connection, pause_requested, contents_rows):
    """One killable worker; pause acknowledges only at a safe booklet boundary."""
    settings = Settings(**settings_values)
    root = Path(directory)
    completed = 0

    def checkpoint():
        if pause_requested.is_set():
            connection.send(("paused", completed))
            while pause_requested.is_set():
                time.sleep(0.05)

    try:
        from pypdf import PdfWriter
        with PdfWriter() as writer:
            checkpoint()
            from .summary_booklet_contents import generate_contents_pdf
            contents = root / "contents.pdf"
            generate_contents_pdf(contents_rows, contents)
            writer.append(str(contents), import_outline=False)
            contents.unlink()
            for person_id in person_ids:
                checkpoint()
                part = root / f"{person_id}.pdf"
                generate_person_booklet_pdf(settings, person_id, output_path=part)
                writer.append(str(part), import_outline=False)
                part.unlink()
                completed += 1
                connection.send(("progress", completed))
            checkpoint()
            writer.add_metadata({"/Title": "Буклеты кавалеров"})
            writer.write(str(root / "summary_booklets.pdf"))
        connection.send(("ready", completed))
    except Exception:
        logger.exception("Summary booklet generation failed")
        connection.send(("failed", completed))
    finally:
        connection.close()


summary_booklet_jobs = SummaryBookletJobs()
