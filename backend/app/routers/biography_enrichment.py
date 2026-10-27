import logging
import sqlite3
import json

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from ..config import get_settings
from ..services import biography_enrichment as service
from ..services import manual_import_review as manual
from ..services import manual_review_choices as choices
from ..services import enrichment_workflow as workflow, enrichment_import_jobs as import_jobs, enrichment_export_jobs as export_jobs
from ..services.dates import format_birth_year_input
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
        context['view'] = workflow.workspace(settings,context['token'])
        context['completed'] = workflow.completed_preview(settings,context['token'],context['view'])
    return templates.TemplateResponse(request, 'biography_enrichment.html',
        {'settings': settings, 'level': level, 'base': BASE, 'row_guidance': service.row_guidance, 'year_label':format_birth_year_input, **context}, status_code=status_code)


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


@router.get(BASE + '/state/{token}')
def workspace_state(request: Request, token: str):
    try:
        view = workflow.workspace(get_settings(),token)
        return templates.TemplateResponse(request,'enrichment_workspace.html',
            {'view':view,'base':BASE,'fields':manual.FIELDS,'year_label':format_birth_year_input},headers={'Cache-Control':'no-store'})
    except service.ValidationError as exc:
        raise HTTPException(409,choices.friendly_error(exc)) from exc


def _operations(raw):
    try:
        values=json.loads(raw)
        if not isinstance(values,list) or any(not isinstance(n,str) for n in values):raise ValueError()
        return values
    except (ValueError,TypeError):
        raise service.ValidationError('Неверный набор принятых решений.')


@router.post(BASE + '/workspace/{token}')
def staged_workspace(request: Request, token: str, operations: str=Form('[]')):
    _same_origin(request)
    try:
        view=workflow.workspace(get_settings(),token,_operations(operations))
        return templates.TemplateResponse(request,'enrichment_workspace.html',{'view':view,'base':BASE,'fields':manual.FIELDS,'year_label':format_birth_year_input},headers={'Cache-Control':'no-store'})
    except service.ValidationError as exc:
        return _review_fragment(request,error=choices.friendly_error(exc),status_code=409)


@router.post(BASE + '/workspace/{token}/plan')
def workspace_plan(request: Request, token: str, revision: str=Form(...), operations: str=Form('[]')):
    _same_origin(request)
    try:
        operation,plan=workflow.prepare_workspace(get_settings(),token,revision,_operations(operations))
        return _review_fragment(request,batch_plan=plan,operation=operation)
    except service.ValidationError as exc:
        return _review_fragment(request,error=choices.friendly_error(exc),status_code=409)


@router.post(BASE + '/review/{token}/{row_number}/stage')
async def stage_review(request: Request, token: str, row_number: int):
    _same_origin(request)
    try:
        operation,plan=await run_in_threadpool(workflow.stage,get_settings(),token,row_number,dict(await request.form()))
        return _review_fragment(request,staged_operation=operation,staged_plan=plan)
    except service.ValidationError as exc:
        return _review_fragment(request,error=choices.friendly_error(exc),status_code=409)


@router.get(BASE + '/confirm/{operation}')
def restored_confirmation(request: Request, operation: str):
    try:
        return _review_fragment(request,**workflow.confirmation(get_settings(),operation))
    except service.ValidationError as exc:
        return _review_fragment(request,error=choices.friendly_error(exc),status_code=409)


@router.post(BASE + '/import/{token}/plan')
def import_plan(request: Request, token: str, revision: str = Form(...), exclude: str = Form('[]')):
    _same_origin(request)
    try:
        try:
            excluded = json.loads(exclude)
            if not isinstance(excluded,list) or any(not isinstance(n,(str,int)) for n in excluded):
                raise ValueError()
        except (ValueError,TypeError):
            raise service.ValidationError('Неверный список отложенных строк. Обновите страницу.')
        operation,plan = workflow.prepare_import(get_settings(),token,revision,excluded)
        return _review_fragment(request,batch_plan=plan,operation=operation)
    except service.ValidationError as exc:
        return _review_fragment(request,error=choices.friendly_error(exc),status_code=409)


@router.post(BASE + '/import/start')
def import_start(request: Request, operation: str=Form(...), confirm: str=Form('')):
    _same_origin(request)
    try:
        if confirm!='yes':raise service.ValidationError('Подтвердите показанные изменения перед импортом.')
        return import_jobs.jobs.start(get_settings(),operation)
    except WriteBlockedError as exc:raise HTTPException(403,str(exc)) from exc
    except service.ValidationError as exc:raise HTTPException(409,choices.friendly_error(exc)) from exc


@router.get(BASE + '/import/operations/{operation}')
def import_status(operation: str):
    try:return import_jobs.jobs.status(get_settings(),operation)
    except service.ValidationError as exc:raise HTTPException(409,choices.friendly_error(exc)) from exc
    except (sqlite3.Error,OSError) as exc:raise HTTPException(503,'Статус временно недоступен. Повторите проверку статуса, не отправляя импорт заново.') from exc


@router.post(BASE + '/import/commit')
def import_commit(request: Request, operation: str = Form(...), confirm: str = Form('')):
    _same_origin(request)
    try:
        if confirm!='yes':
            raise service.ValidationError('Подтвердите показанные изменения перед импортом.')
        result = workflow.commit_import(get_settings(),operation)
        return _review_fragment(request,batch_result=result)
    except WriteBlockedError as exc:
        return _review_fragment(request,error=str(exc),status_code=403)
    except service.ValidationError as exc:
        return _review_fragment(request,error=choices.friendly_error(exc),status_code=409)
    except (sqlite3.Error,OSError):
        logging.getLogger(__name__).exception('Enrichment batch transaction failure')
        return _review_fragment(request,error='Импорт не подтверждён. Повторите это же подтверждение: повторная запись исключена. При ошибке транзакции все изменения отменены.',status_code=503)


def _review_fragment(request, **context):
    return templates.TemplateResponse(request, 'manual_import_review.html',
        {'base': BASE, 'fields': manual.FIELDS, 'decisions': manual.DECISIONS, 'review_complete': choices.complete,'year_label':format_birth_year_input, **context},
        status_code=context.get('status_code', 200), headers={'Cache-Control': 'no-store'})


def _same_origin(request):
    if request.headers.get('origin') and request.headers['origin'] != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Подтверждение должно выполняться из этого приложения.')


@router.get(BASE + '/review/{token}/{row_number}')
def review_row(request: Request, token: str, row_number: int):
    try:
        return _review_fragment(request, review=choices.detail(get_settings(), token, row_number))
    except service.ValidationError as exc:
        return _review_fragment(request, error=choices.friendly_error(exc), status_code=409)
    except (sqlite3.Error, OSError):
        return _review_fragment(request, error='Проверка недоступна: не удалось прочитать базу или журнал. Изменений нет.', status_code=503)


@router.post(BASE + '/review/{token}/{row_number}/plan')
async def review_plan(request: Request, token: str, row_number: int):
    _same_origin(request)
    values = dict(await request.form())
    try:
        plan_token, plan = await run_in_threadpool(choices.prepare, get_settings(), token, row_number, values)
        return _review_fragment(request, plan_token=plan_token, plan=plan)
    except service.ValidationError as exc:
        return _review_fragment(request, error=choices.friendly_error(exc), status_code=400)
    except (sqlite3.Error, OSError):
        return _review_fragment(request, error='Не удалось подготовить план. Изменений в базе нет; повторите проверку.', status_code=503)


@router.get(BASE + '/review/{token}/{row_number}/history')
def review_history(request: Request, token: str, row_number: int):
    try:
        return _review_fragment(request, history=workflow.history_view(manual.reviewed_history(get_settings(), token, row_number)))
    except service.ValidationError as exc:
        return _review_fragment(request, error=choices.friendly_error(exc), status_code=409)
    except (sqlite3.Error, OSError):
        return _review_fragment(request, error='Не удалось прочитать журнал проверки.', status_code=503)


@router.get(BASE + '/review-history')
def durable_review_history(request: Request, person_id: int | None = None):
    try:
        return _review_fragment(request, history=workflow.history_view(manual.durable_history(get_settings(), person_id)), durable=True)
    except service.ValidationError as exc:
        return _review_fragment(request, error=choices.friendly_error(exc), status_code=409)
    except (sqlite3.Error, OSError):
        return _review_fragment(request, error='Не удалось прочитать журнал проверки.', status_code=503)


@router.post(BASE + '/review/commit')
def review_commit(request: Request, plan_token: str = Form(...), confirm: str = Form('')):
    _same_origin(request)
    try:
        if confirm != 'yes':
            raise service.ValidationError('Подтвердите точный набор изменений перед записью.')
        event = workflow.commit_review(get_settings(), plan_token)
        review = workflow.result_state(get_settings(),event)
        return _review_fragment(request, event=event, updated=review)
    except WriteBlockedError as exc:
        return _review_fragment(request, error=str(exc), status_code=403)
    except service.ValidationError as exc:
        return _review_fragment(request, error=choices.friendly_error(exc), status_code=409)
    except (sqlite3.Error, OSError):
        logging.getLogger(__name__).exception('Manual review transaction failure')
        return _review_fragment(request, error='Не удалось подтвердить сохранение. Повторите этот же запрос: журнал предотвратит повторную запись. При ошибке транзакции все поля и аудит откатываются вместе.', status_code=503)


@router.get(BASE + '/statistics')
def statistics():
    try:
        return service.population_statistics(get_settings())
    except (sqlite3.Error, OSError) as exc:
        raise HTTPException(503, 'Не удалось обновить статистику базы.') from exc


@router.post(BASE + '/export/start')
def export_start(request: Request, operation: str = Form(...), selection: str = Form(''), limit: int = Form(20)):
    _same_origin(request)
    try:
        return export_jobs.jobs.start(get_settings(), operation, selection, limit)
    except service.ValidationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get(BASE + '/export/operations/{operation}')
def export_status(operation: str):
    try:
        return export_jobs.jobs.status(get_settings(), operation)
    except service.ValidationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get(BASE + '/export/operations/{operation}/file')
def export_download(operation: str):
    try:
        content = export_jobs.jobs.download(get_settings(), operation)
    except (service.ValidationError, OSError) as exc:
        raise HTTPException(409, str(exc)) from exc
    return Response(content, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': 'attachment; filename="biographies.xlsx"', 'Cache-Control': 'no-store'})


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
        result['filename'] = file.filename
        service._save(get_settings(),token,result)
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
        result = workflow.commit_ordinary(get_settings(), token)
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
    view = workflow.present(get_settings(),token)
    payload = {name: result[name] for name in ('created', 'state', 'file_sha256')}
    payload.update(ready=view['ready'],confirmed=view['confirmed'],pending=view['pending'],
                   rows=[{'person_id':r['person_id'],'fio':r['fio'],'status':r['status'],'reason':r['reason']} for r in view['rows']])
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
    return Response(workflow.report(get_settings(),token),
                    media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': 'attachment; filename="biographies-report.xlsx"', 'Cache-Control': 'no-store'})
