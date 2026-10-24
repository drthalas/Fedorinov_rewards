import logging
import sqlite3

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from ..config import get_settings
from ..services import biography_enrichment as service
from ..services import manual_import_review as manual
from ..services.write_guard import WriteBlockedError
from .templates import templates

router = APIRouter()
BASE = '/data-maintenance/enrichment/biographies'


def _render(request, *, level='biographies', status_code=200, **context):
    settings = get_settings()
    if level == 'biographies' and 'stats' not in context:
        try:
            context['stats'] = service.statistics(settings)
        except sqlite3.Error:
            context.update(stats=None, error='Не удалось прочитать биографии из базы. Проверьте доступность базы и наличие поля biography.')
            status_code = 503
    if context.get('result'):
        context['groups'] = service.review_groups(context['result'])
        context['saved_rows'] = [row for row in context['result']['rows'] if row['kind'] == 'Сохранено']
        try:
            context['manual_summaries'] = manual.summaries(settings, context['result']['file_sha256'])
        except (sqlite3.Error, OSError, ValueError, KeyError):
            context['manual_summaries'] = {}
    return templates.TemplateResponse(request, 'biography_enrichment.html',
        {'settings': settings, 'level': level, 'base': BASE, 'row_guidance': service.row_guidance, **context}, status_code=status_code)


@router.get('/data-maintenance')
def maintenance(request: Request):
    return _render(request, level='maintenance')


@router.get('/data-maintenance/enrichment')
def enrichment(request: Request):
    return _render(request, level='enrichment')


@router.get(BASE)
def biographies(request: Request, selection: str = ''):
    return _render(request, selection=selection)


@router.get(BASE + '/preview/{token}')
def restored_preview(request: Request, token: str):
    try:
        return _render(request, token=token, result=service.load_preview(get_settings(), token))
    except service.ValidationError as exc:
        return _render(request, error=str(exc), status_code=400)


def _review_fragment(request, **context):
    return templates.TemplateResponse(request, 'manual_import_review.html',
        {'base': BASE, 'fields': manual.FIELDS, 'decisions': manual.DECISIONS, **context},
        status_code=context.get('status_code', 200), headers={'Cache-Control': 'no-store'})


def _same_origin(request):
    if request.headers.get('origin') and request.headers['origin'] != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Подтверждение должно выполняться из этого приложения.')


@router.get(BASE + '/review/{token}/{row_number}')
def review_row(request: Request, token: str, row_number: int):
    try:
        return _review_fragment(request, review=manual.review(get_settings(), token, row_number))
    except service.ValidationError as exc:
        return _review_fragment(request, error=str(exc), status_code=409)
    except (sqlite3.Error, OSError):
        return _review_fragment(request, error='Проверка недоступна: не удалось прочитать базу или журнал. Изменений нет.', status_code=503)


@router.post(BASE + '/review/{token}/{row_number}/plan')
async def review_plan(request: Request, token: str, row_number: int):
    _same_origin(request)
    values = dict(await request.form())
    try:
        plan_token, plan = await run_in_threadpool(manual.prepare, get_settings(), token, row_number, values)
        return _review_fragment(request, plan_token=plan_token, plan=plan)
    except service.ValidationError as exc:
        return _review_fragment(request, error=str(exc), status_code=400)
    except (sqlite3.Error, OSError):
        return _review_fragment(request, error='Не удалось подготовить план. Изменений в базе нет; повторите проверку.', status_code=503)


@router.get(BASE + '/review/{token}/{row_number}/history')
def review_history(request: Request, token: str, row_number: int):
    try:
        return _review_fragment(request, history=manual.reviewed_history(get_settings(), token, row_number))
    except service.ValidationError as exc:
        return _review_fragment(request, error=str(exc), status_code=409)
    except (sqlite3.Error, OSError):
        return _review_fragment(request, error='Не удалось прочитать журнал проверки.', status_code=503)


@router.get(BASE + '/review-history')
def durable_review_history(request: Request, person_id: int | None = None):
    try:
        return _review_fragment(request, history=manual.durable_history(get_settings(), person_id), durable=True)
    except service.ValidationError as exc:
        return _review_fragment(request, error=str(exc), status_code=409)
    except (sqlite3.Error, OSError):
        return _review_fragment(request, error='Не удалось прочитать журнал проверки.', status_code=503)


@router.post(BASE + '/review/commit')
def review_commit(request: Request, plan_token: str = Form(...), confirm: str = Form('')):
    _same_origin(request)
    try:
        if confirm != 'yes':
            raise service.ValidationError('Подтвердите точный набор изменений перед записью.')
        event = manual.commit(get_settings(), plan_token)
        return _review_fragment(request, event=event)
    except WriteBlockedError as exc:
        return _review_fragment(request, error=str(exc), status_code=403)
    except service.ValidationError as exc:
        return _review_fragment(request, error=str(exc), status_code=409)
    except (sqlite3.Error, OSError):
        logging.getLogger(__name__).exception('Manual review transaction failure')
        return _review_fragment(request, error='Не удалось подтвердить сохранение. Повторите этот же запрос: журнал предотвратит повторную запись. При ошибке транзакции все поля и аудит откатываются вместе.', status_code=503)


@router.get(BASE + '/export')
def export(request: Request, selection: str = '', limit: int = 20):
    try:
        content = service.export_workbook(get_settings(), selection, limit)
    except service.ValidationError as exc:
        return _render(request, error=str(exc), selection=selection, status_code=400)
    return Response(content, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': 'attachment; filename="biographies.xlsx"', 'Cache-Control': 'no-store'})


@router.post(BASE + '/preview')
async def preview(request: Request, file: UploadFile = File(...), original: UploadFile | None = File(None)):
    try:
        if not (file.filename or '').lower().endswith('.xlsx'):
            raise service.ValidationError('Поддерживается только формат .xlsx.')
        content = await file.read(service.MAX_BYTES + 1)
        source = None
        if original is not None and original.filename:
            if not original.filename.lower().endswith('.xlsx'):
                raise service.ValidationError('Исходная выгрузка должна быть в формате .xlsx.')
            source = await original.read(service.MAX_BYTES + 1)
        token, result = await run_in_threadpool(service.preview, get_settings(), content, source)
        return _render(request, token=token, result=result)
    except service.ValidationError as exc:
        return _render(request, error=str(exc), status_code=400)
    finally:
        await file.close()
        if original is not None:
            await original.close()


@router.post(BASE + '/commit')
def commit(request: Request, token: str = Form(...), confirm: str = Form('')):
    if request.headers.get('origin') and request.headers['origin'] != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Подтверждение должно выполняться из этого приложения.')
    try:
        if confirm != 'yes':
            raise service.ValidationError('Подтвердите сохранение только допустимых строк.')
        result = service.commit(get_settings(), token)
        return _render(request, token=token, result=result)
    except WriteBlockedError as exc:
        return _render(request, error=str(exc), status_code=403)
    except service.ValidationError as exc:
        return _render(request, error=str(exc), status_code=400)
    except (sqlite3.Error, OSError):
        logging.getLogger(__name__).exception('Biography transaction/report failure')
        return _render(request, error='Сохранение не завершено. Все неподтверждённые изменения транзакции отменены. Загрузите файл для новой проверки.', status_code=503)


@router.get(BASE + '/report/{token}')
def report(token: str):
    try:
        result = service.load_preview(get_settings(), token)
    except service.ValidationError as exc:
        raise HTTPException(404, str(exc)) from exc
    # A crash between report preparation and SQLite commit has an explicitly
    # uncertain outcome. It must never be reported as a confirmed write.
    if result['state'] == 'commit_pending':
        result['warning'] = 'Результат транзакции не подтверждён. Нужен новый preview текущей базы.'
    payload = {name: result[name] for name in ('created', 'state', 'file_sha256', 'ready', 'saved', 'rows')}
    if result.get('warning'):
        payload['warning'] = result['warning']
    return Response(service.canonical(payload), media_type='application/json',
                    headers={'Content-Disposition': 'attachment; filename="biographies-report.json"', 'Cache-Control': 'no-store'})


@router.get(BASE + '/report/{token}/excel')
def excel_report(token: str):
    try:
        result = service.load_preview(get_settings(), token)
    except service.ValidationError as exc:
        raise HTTPException(404, str(exc)) from exc
    if result['state'] == 'commit_pending':
        raise HTTPException(409, 'Результат сохранения не подтверждён. Загрузите файл для новой проверки текущей базы.')
    return Response(service.report_workbook(result),
                    media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': 'attachment; filename="biographies-report.xlsx"', 'Cache-Control': 'no-store'})
