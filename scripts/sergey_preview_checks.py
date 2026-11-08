"""Fixed focused-check harness; product writes/browser actions are isolated to synthetic TEMP."""
import argparse
import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request


def main():
    p=argparse.ArgumentParser();p.add_argument('--worktree',type=Path,required=True);p.add_argument('--plan',type=Path,required=True);p.add_argument('--node-module',required=True);p.add_argument('--dependency-dir',default='');a=p.parse_args();plan=json.loads(a.plan.read_text());work=a.worktree.resolve()
    if a.dependency_dir:sys.path.insert(0,a.dependency_dir)
    with tempfile.TemporaryDirectory(prefix='owner-preview-focus-') as temp:
        root=Path(temp);env={k:v for k,v in os.environ.items() if not any(x in k.upper() for x in ['TOKEN','API_KEY','TELEGRAM','LINEAR','SERGEY_','REWARDS_','UPDATE_'])}
        env.update(REWARDS_DATA_DIR=str(root),REWARDS_DB_PATH=str(root/'database.sqlite'),APP_INSTALL_DIR=str(root),APP_RUNTIME_DIR=str(root/'runtime'),UPDATE_CHECK_ENABLED='false',WRITE_MODE='true',READ_ONLY='false',HTTP_PROXY='http://127.0.0.1:9',HTTPS_PROXY='http://127.0.0.1:9',NO_PROXY='127.0.0.1,localhost')
        if a.dependency_dir:env['PYTHONPATH']=a.dependency_dir
        for test in plan['tests']:subprocess.run([sys.executable,'-m','unittest',test,'-q'],cwd=work,env=env,check=True,timeout=60)
        if not plan['browser_path']:return
        route=plan['browser_path']
        if not route.startswith('/') or route.startswith('//') or any(x in route.lower() for x in ['updat','enrichment','import','delete','recovery']):raise RuntimeError('unsafe_browser_route')
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        startup=root/'server.py'
        startup.write_text('''import os,sys,sqlite3,base64
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from tests.test_person_detail_return import PersonDetailReturnTests
fixture=PersonDetailReturnTests();fixture.setUp()
r=fixture.root
for n in ['Source','SourceMark','default','GuideImages']:(r/n).mkdir(exist_ok=True)
(r/'default/nofoto.jpg').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6VwAAAABJRU5ErkJggg=='))
with sqlite3.connect(fixture.db_path) as db:
 db.execute('CREATE TABLE IF NOT EXISTS guide_lev_4(id integer primary key, idl integer, name text)')
 db.execute('CREATE TABLE IF NOT EXISTS mark(id integer primary key,name text)')
os.environ['UPDATE_CHECK_ENABLED']='false'
import uvicorn
uvicorn.run('backend.app.main:app',host='127.0.0.1',port=int(sys.argv[2]),log_level='error')
''')
        log=(root/'server.log').open('w');server=subprocess.Popen([sys.executable,str(startup),str(work),str(port)],cwd=work,env=env,stdout=log,stderr=log)
        try:
            for _ in range(100):
                if server.poll() is not None:raise RuntimeError('temp_browser_runtime_failed')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=1) as response:
                        if response.status==200:break
                except Exception:time.sleep(.1)
            else:raise RuntimeError('temp_runtime_timeout')
            node=root/'browser.cjs';node.write_text('''const fs=require('fs'); const {chromium}=require(process.argv[2]);
(async()=>{const plan=JSON.parse(fs.readFileSync(process.argv[3]));const origin=process.argv[4];const browser=await chromium.launch({channel:'chrome',headless:true});
try {const context=await browser.newContext();await context.route('**/*',r=>new URL(r.request().url()).origin===origin?r.continue():r.abort());const page=await context.newPage();
const response=await page.goto(origin+plan.browser_path);if(!response||response.status()>=400)throw Error('Browser route failed');
for(const step of plan.browser_actions){if(!['link','button','textbox','searchbox'].includes(step.role))throw Error('Invalid role');const target=page.getByRole(step.role,{name:step.name,exact:true});
if(step.action==='fill'){await target.fill(step.value);}else if(step.action==='click'){const href=await target.getAttribute('href');if(href&&new URL(href,origin).origin!==origin)throw Error('External navigation forbidden');await target.click();}else throw Error('Invalid action');}
if(plan.expect_text)await page.getByText(plan.expect_text,{exact:false}).first().waitFor({state:'visible',timeout:10000});console.log('Focused TEMP browser PASS');}
finally {await browser.close();}})().catch(e=>{console.error(e.name);process.exitCode=1;});''')
            subprocess.run(['node',str(node),a.node_module,str(a.plan),f'http://127.0.0.1:{port}'],cwd=work,env=env,check=True,timeout=70)
        finally:
            server.terminate()
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:server.kill();server.wait()
            log.close()

if __name__=='__main__':main()
