"""Versioned and bounded reassessment of only the original five; no DB access."""
import argparse
import hashlib
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse
from research import SCHEMA,load_xlsx,validate,reevaluation_prompt,public_profile_url
from runner import command,events_summary,subscription_environment,source_was_opened


def prior_candidates(root,index,row):
    candidates=[]
    surname=row['ФИО'].split()[0].casefold().replace('ё','е')
    for line in (root/f'events-{index:02}.jsonl').read_text().splitlines():
        event=json.loads(line);item=event.get('item',{})
        if event.get('type')!='item.completed' or item.get('action',{}).get('type')!='search':continue
        for r in item.get('results',[]):
            url=r.get('url','');title=r.get('title','').casefold().replace('ё','е')
            if surname in title and public_profile_url(url):candidates.append(url)
    # Wikipedia and explicit profile references before previously unavailable archive cards.
    return sorted(set(candidates),key=lambda url:('pamyat-naroda.ru' in url or 'podvignaroda.ru' in url,url))[:3]


def run(root,out,model='gpt-6-sol',timeout=120,max_web_calls=3):
    root=Path(root);out=Path(out);out.mkdir(parents=True,exist_ok=True,mode=0o700)
    rows=load_xlsx(root/'input.xlsx')
    assert len(rows)==50 and len({r['person_id'] for r in rows})==50
    digest=hashlib.sha256((root/'input.xlsx').read_bytes()).hexdigest()
    progress_path=out/'progress.json';telemetry_path=out/'telemetry.json'
    progress=json.loads(progress_path.read_text()) if progress_path.exists() else json.loads((root/'progress.json').read_text())
    telemetry=json.loads(telemetry_path.read_text()) if telemetry_path.exists() else {'input_sha256':digest,'runs':[],'scope':'original first5 only','model':model,'external_paid_cost':0}
    if telemetry['input_sha256']!=digest:raise ValueError('Frozen input changed')
    schema=out/'schema.json';schema.write_text(json.dumps(SCHEMA))
    for index,row in enumerate(rows[:5],1):
        if progress[row['person_id']].get('evaluation_policy')=='exact-fio-birth-award-v1' and progress[row['person_id']].get('attempt_state')=='completed':continue
        key=row['person_id'];candidates=prior_candidates(root,index,row)
        attempt=1+sum(r['row']==index for r in telemetry['runs'])
        events=out/f'events-{index:02}-attempt{attempt}.jsonl';last=out/f'result-{index:02}-attempt{attempt}.json';error=out/f'stderr-{index:02}-attempt{attempt}.txt'
        start=time.monotonic();budget_error='';usage={};proc=None
        with events.open('w') as stdout,error.open('w') as stderr:
            proc=subprocess.Popen(command(model,out,schema,last,slim=True),stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,
              text=True,env=subscription_environment(),start_new_session=True)
            proc.stdin.write(reevaluation_prompt(row,candidates));proc.stdin.close()
            while proc.poll() is None:
                summary=events_summary(events)
                if summary['web_calls']>max_web_calls or time.monotonic()-start>timeout:
                    budget_error='Bounded web/time budget exceeded'
                    os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=5);break
                time.sleep(0.5)
        summary=events_summary(events)
        result={'person_id':key,'biography':'','source_urls':[],'identity':[],'evidence':[],'status':'Ошибка источника','notes':budget_error or 'No accessible verified person profile','confidence':'none'}
        if proc.returncode==0 and last.exists():
            candidate=json.loads(last.read_text())
            try:
                candidate=validate(candidate,{**row,'person_id':'row-'+row['sample_order']})
                if candidate['biography'] and not all(source_was_opened(u,summary['opened_urls']) for u in candidate['source_urls']):raise ValueError('Cited profile was not actually opened')
                candidate['person_id']=key;result=candidate
            except ValueError as exc:
                result['status']='Требует проверки';result['notes']='Draft rejected by explicit matching/source rule: '+str(exc)
        result['evaluation_policy']='exact-fio-birth-award-v1'
        result['attempt_state']='completed' if proc.returncode==0 else 'infrastructure_blocked'
        progress[key]=result
        telemetry['runs'].append({'row':index,'model':model,'elapsed_seconds':round(time.monotonic()-start,2),
          'usage':summary['usage'],'web_calls':summary['web_calls'],'compactions':summary['compactions'],'status':result['status'],
          'confidence':result.get('confidence','none'),'biography_chars':len(result['biography']),'budget_error':budget_error,'candidate_urls_reused':len(candidates),'errors':summary['errors'],'attempt':attempt,'returncode':proc.returncode})
        progress_path.write_text(json.dumps(progress,ensure_ascii=False,indent=2));telemetry_path.write_text(json.dumps(telemetry,ensure_ascii=False,indent=2))
        for p in (progress_path,telemetry_path,events,last,error,schema):
            if p.exists():p.chmod(0o600)
        print(json.dumps({k:telemetry['runs'][-1][k] for k in ('row','status','confidence','biography_chars','elapsed_seconds','web_calls')},ensure_ascii=False),flush=True)
        if proc.returncode!=0 and not budget_error:raise RuntimeError('BLOCKED: subscription execution failure; inspect private stderr')
    return progress,telemetry


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--private-root',required=True);p.add_argument('--out',required=True);p.add_argument('--model',default='gpt-6-sol');p.add_argument('--timeout',type=int,default=120);p.add_argument('--max-web-calls',type=int,default=3)
    a=p.parse_args();run(a.private_root,a.out,a.model,a.timeout,a.max_web_calls)
