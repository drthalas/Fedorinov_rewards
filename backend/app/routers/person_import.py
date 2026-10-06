import logging
import sqlite3

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from ..config import get_settings
from ..repositories.reward_reference import get_reward_reference, list_reward_references
from ..services.person_import import ImportValidationError, MAX_UPLOAD_BYTES, import_persons
from ..services.write_guard import WriteBlockedError, ensure_write_allowed
from .templates import templates

router = APIRouter()


def _settings():
    settings = get_settings()
    try:
        ensure_write_allowed(settings)
    except WriteBlockedError as exc:
        raise HTTPException(403, str(exc)) from exc
    if not settings.db_exists:
        raise HTTPException(404, 'База данных не найдена.')
    return settings


def _render(request, settings, name_id=None, *, error=None, result=None, status_code=200):
    reference = get_reward_reference(settings.rewards_db_path, name_id) if name_id else None
    return templates.TemplateResponse(request, 'person_import.html', {
        'settings': settings, 'reference': reference, 'error': error, 'result': result,
        'reward_references': list_reward_references(settings.rewards_db_path) if not reference else [],
    }, status_code=status_code)


@router.get('/persons/import')
def person_import_page(request: Request, id_name: int | None = None):
    settings = _settings()
    if id_name is not None and get_reward_reference(settings.rewards_db_path, id_name) is None:
        return _render(request, settings, error='Выберите существующую награду.', status_code=400)
    return _render(request, settings, id_name)


@router.post('/persons/import')
async def person_import_upload(request: Request, id_name: int = Form(...), confirm: str = Form(''), file: UploadFile = File(...)):
    settings = _settings()
    try:
        if confirm != 'yes':
            raise ImportValidationError('Подтвердите добавление кавалеров для выбранной награды.')
        if not (file.filename or '').lower().endswith('.xlsx'):
            raise ImportValidationError('Выберите файл в формате .xlsx.')
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        result = await run_in_threadpool(import_persons, settings, id_name, content)
    except ImportValidationError as exc:
        return _render(request, settings, id_name, error=str(exc), status_code=400)
    except sqlite3.Error:
        logging.getLogger(__name__).exception('XLSX import transaction failed')
        return _render(request, settings, id_name, error='Импорт не сохранён: ошибка базы данных. Все изменения этого файла отменены. Повторите попытку.', status_code=503)
    finally:
        await file.close()
    return _render(request, settings, id_name, result=result)
