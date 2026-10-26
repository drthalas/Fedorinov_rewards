"""A nonblocking, process-shared lease for import/correction, outside SQLite/media."""
from contextlib import contextmanager
import os
from . import biography_enrichment as bio
from .write_guard import WriteBlockedError

@contextmanager
def exclusive(settings):
    path=bio._state(settings)/'data-operation.lock'
    handle=open(path,'a+b')
    try:
        if os.name=='nt':
            import msvcrt
            handle.seek(0,2)
            if not handle.tell():handle.write(b'0');handle.flush()
            handle.seek(0)
            try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as exc:raise WriteBlockedError('Выполняется импорт или исправление данных. Дождитесь завершения.') from exc
        else:
            import fcntl
            try:fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc:raise WriteBlockedError('Выполняется импорт или исправление данных. Дождитесь завершения.') from exc
        yield
    finally:
        # Closing releases either OS lock even on exceptions/process exit.
        handle.close()
