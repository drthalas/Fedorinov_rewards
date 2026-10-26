from fastapi import APIRouter,Request,Form,HTTPException
from ..config import get_settings
from ..services import fio_corrections as service, biography_enrichment as bio
from ..services.write_guard import WriteBlockedError
from .biography_enrichment import _same_origin
from .templates import templates

router=APIRouter();BASE='/data-maintenance/corrections'

@router.get(BASE)
def page(request:Request):
    return templates.TemplateResponse(request,'fio_corrections.html',{'settings':get_settings(),'base':BASE})

@router.post(BASE+'/jobs')
def start(request:Request,kind:str=Form(...),request_id:str=Form(...),audit_token:str|None=Form(None)):
    _same_origin(request)
    try:return service.jobs.start(get_settings(),kind,request_id,audit_token)
    except (bio.ValidationError,WriteBlockedError) as exc:raise HTTPException(409,str(exc)) from exc

@router.get(BASE+'/jobs/{job}')
def status(job:str):
    try:return service.jobs.status(get_settings(),job)
    except bio.ValidationError as exc:raise HTTPException(404,str(exc)) from exc

@router.get(BASE+'/preview/{token}')
def preview(request:Request,token:str,page:int=1):
    try:plan=service.load_audit(get_settings(),token)
    except bio.ValidationError as exc:raise HTTPException(409,str(exc)) from exc
    pages=max(1,(len(plan['rows'])+49)//50);page=max(1,min(page,pages))
    rows=[]
    for row in plan['rows'][(page-1)*50:page*50]:
        fields=[]
        for name,before in row['before'].items():
            after=row['after'][name]
            if not before and not after:continue
            before='' if before is None else str(before);after='' if after is None else str(after)
            fields.append({'name':name,'before':[{'text':c,'changed':i<len(after) and c!=after[i]} for i,c in enumerate(before)],
                'after':[{'text':c,'changed':i<len(before) and c!=before[i]} for i,c in enumerate(after)]})
        rows.append({**row,'fields':fields})
    return templates.TemplateResponse(request,'fio_corrections_preview.html',{'plan':plan,'rows':rows,'page':page,'pages':pages,'token':token,'base':BASE},headers={'Cache-Control':'no-store'})
