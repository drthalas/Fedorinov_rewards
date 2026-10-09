"""Subscription-only CLI commands, telemetry and a non-personal model smoke."""
import argparse
import json
import os
import subprocess
import time
import tomllib
from pathlib import Path


def subscription_environment():
    env=os.environ.copy()
    # Never allow inherited API keys to override the saved ChatGPT login.
    for key in ('OPENAI_API_KEY','CODEX_API_KEY'):
        env.pop(key,None)
    return env


def command(model,directory,schema,last_message):
    if not model or not isinstance(model,str):raise ValueError('Explicit smoke-verified subprocess model required')
    # Research uses native web only; unrelated configured connectors must not start.
    config=Path.home()/'.codex/config.toml'
    servers=tomllib.loads(config.read_text()).get('mcp_servers',{}) if config.exists() else {}
    overrides=[arg for name in servers for arg in ('-c',f'mcp_servers.{name}.enabled=false')]
    return ['codex','--no-daemon','--search',*overrides,'exec','--ephemeral','--sandbox','read-only',
      '--skip-git-repo-check','--json','-m',model,'-C',str(directory),'--output-schema',str(schema),'-o',str(last_message),'-']


def events_summary(path):
    result={'usage':{},'tool_calls':0,'web_calls':0,'compactions':0,'errors':[],'opened_urls':[]}
    if not Path(path).exists():return result
    for line in Path(path).read_text().splitlines():
        try:event=json.loads(line)
        except json.JSONDecodeError:continue
        if event.get('type')=='turn.completed':result['usage']=event.get('usage',{})
        item=event.get('item',{});kind=item.get('type','')
        if event.get('type')=='item.completed' and kind in ('web_search','command_execution','mcp_tool_call'):result['tool_calls']+=1
        if event.get('type')=='item.completed' and kind=='web_search':result['web_calls']+=1
        if event.get('type')=='item.completed' and kind=='web_search' and item.get('action',{}).get('type')=='open_page':
            for source in item.get('results',[]):
                if source.get('type')=='text_result' and source.get('url') and source.get('title'):
                    result['opened_urls'].append(source['url'])
        if 'compact' in str(event.get('type','')).lower():result['compactions']+=1
        if event.get('type') in ('error','turn.failed'):
            result['errors'].append(event.get('message') or event.get('error',{}).get('message','unknown'))
    return result


def smoke(model,directory,timeout=90):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    schema=directory/'smoke_schema.json';schema.write_text(json.dumps({'type':'object','properties':{
      'synthetic_answer':{'type':'integer'},'source_accessible':{'type':'boolean'},'visited_url':{'type':'string'},'page_title':{'type':'string'}},
      'required':['synthetic_answer','source_accessible','visited_url','page_title'],'additionalProperties':False}))
    events=directory/f'smoke-{model}.jsonl';last=directory/f'smoke-{model}.result.json';err=directory/f'smoke-{model}.stderr'
    start=time.monotonic();status='FAIL';error='';response={}
    auth=subprocess.run(['codex','login','status'],env=subscription_environment(),text=True,capture_output=True)
    if 'ChatGPT' not in auth.stdout+auth.stderr:raise RuntimeError('STOP: saved CLI authentication is not ChatGPT')
    prompt='Synthetic non-personal smoke. Compute 7+8. Use web search and actually open https://warheroes.ru/ (or https://pamyat-naroda.ru/ if first is inaccessible). Return synthetic_answer=15 and source_accessible=true only if an actual webpage was opened. Include its real URL/title. Do not read files, run shell, access connectors, upload anything, or contact people.'
    try:
        with events.open('w') as output,err.open('w') as stderr:
            p=subprocess.run(command(model,directory,schema,last),input=prompt,text=True,env=subscription_environment(),stdout=output,stderr=stderr,timeout=timeout)
        summary=events_summary(events)
        if p.returncode or not last.exists():error='; '.join(summary['errors']) or 'CLI failed'
        else:
            response=json.loads(last.read_text())
            if response['synthetic_answer']==15 and response['source_accessible'] and summary['web_calls']>0 and summary['usage']:
                status='PASS'
            else:error='Inference/web smoke conditions not satisfied'
    except subprocess.TimeoutExpired:error='Synthetic smoke timed out'
    summary=events_summary(events)
    result={'model':model,'auth_mode':'ChatGPT','status':status,'elapsed_seconds':round(time.monotonic()-start,2),'error':error,'response':response,**summary}
    report=directory/f'smoke-{model}.summary.json';report.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    for file in (schema,events,last,err,report):
        if file.exists():file.chmod(0o600)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--private-dir',required=True);p.add_argument('--timeout',type=int,default=90)
    a=p.parse_args();r=smoke(a.model,a.private_dir,a.timeout)
    print(json.dumps(r,ensure_ascii=False));raise SystemExit(0 if r['status']=='PASS' else 1)
