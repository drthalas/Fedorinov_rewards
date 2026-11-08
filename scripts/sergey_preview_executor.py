"""Controlled T1/T2 product edits and preview-only deployment. Model has no tools."""
import ast
import base64
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import time
import urllib.parse

try:
    from .sergey_delivery_railway import PreviewAdapter,FINGERPRINT,media_check_mode
    from .sergey_delivery import DeliveryBlocked,ROOT
    from .sergey_intake import safe_text
except ImportError:
    from sergey_delivery_railway import PreviewAdapter,FINGERPRINT,media_check_mode
    from sergey_delivery import DeliveryBlocked,ROOT
    from sergey_intake import safe_text

DENY_PATH=re.compile(r'(^|/)(?:config|db|version|auth|security|updater|recovery|runtime|migration|signing|enrichment|delete|backup)|AGENTS|CODEX_START|LINEAR_PROCESS|RELEASES|CHANGELOG|WINDOWS|RECOVERY|UPDATE_SYSTEM|\.github|sergey_',re.I)
DANGER=re.compile(r'UPDATE\s+\w+\s+SET|DELETE\s+FROM|INSERT\s+INTO|DROP\s+TABLE|ALTER\s+TABLE|sqlite3|\.unlink\s*\(|rmtree\s*\(|os\.remove|\b(password|secret|signing|csrf|auth|token|subprocess)\b|\b(eval|exec)\s*\(|https?://|WebSocket|XMLHttpRequest|sendBeacon|\bfetch\s*\(',re.I)


def allowed(path):
    p=Path(path)
    if p.is_absolute() or '..' in p.parts or DENY_PATH.search(path):return False
    return (path in {'HELP_RU.md','README.md'} or (path.startswith('docs/') and not path.startswith('docs/context/') and p.suffix=='.md')
            or path.startswith('backend/app/templates/') and p.suffix=='.html'
            or path.startswith('backend/app/static/') and p.suffix in {'.css','.js'}
            or path.startswith('backend/app/routers/') and p.suffix=='.py')


def proposed_files(work,edits,base_texts=None):
    if not 1<=len(edits)<=12:raise DeliveryBlocked('edit_count_outside_scope')
    result={};before={}
    for edit in edits:
        path=edit['path'];old=edit['old'];new=edit['new'];target=work/path
        if not allowed(path) or target.is_symlink() or not target.resolve().is_relative_to(work.resolve()):raise DeliveryBlocked('protected_or_invalid_product_path')
        if len(old)+len(new)>50000 or safe_text(new)!=new:raise DeliveryBlocked('unsafe_or_oversized_edit')
        if path not in before:before[path]=base_texts[path] if base_texts is not None else (target.read_text() if target.exists() else None)
        text=result.get(path,before[path])
        if text is None:
            if old:raise DeliveryBlocked('new_file_old_text_not_empty')
            result[path]=new
        else:
            if not old or text.count(old)!=1:raise DeliveryBlocked('replacement_not_unique')
            result[path]=text.replace(old,new,1)
    diff='\n'.join(''.join(difflib.unified_diff((before[p] or '').splitlines(True),text.splitlines(True),fromfile=p,tofile=p)) for p,text in result.items())
    changed='\n'.join(line[1:] for line in diff.splitlines() if line[:1] in {'+','-'} and not line.startswith(('+++','---')))
    if DANGER.search(changed):raise DeliveryBlocked('protected_or_network_change_requires_owner')
    tier='T1' if all(Path(p).suffix=='.md' or (Path(p).suffix=='.html' and not re.search(r'[<>{}=]',e['old']+e['new'])) for p in result for e in edits if e['path']==p) else 'T2'
    return result,diff,tier


class DynamicPreviewAdapter(PreviewAdapter):
    def __init__(self,state,config,credentials):
        super().__init__(state,config,credentials)
        self.source_folder=self.folder/'source'
        self.folder=self.folder/f"build-r{self.pilot['revision']}";self.folder.mkdir(exist_ok=True,mode=0o700)

    def command(self,args,cwd=None,timeout=60):
        try:return super().command(args,cwd=cwd,timeout=timeout)
        except Exception as error:
            if args[0] in {'railway','ssh','git','node'}:
                operation='_'.join(str(a) for a in args[:4] if re.fullmatch('[a-z_-]+',str(a)))
                raise DeliveryBlocked('preview_'+operation.replace('-','_')+'_failed') from None
            raise

    def guard(self,job):self.state.guard(job)

    def model(self,prompt,schema,destination):
        if destination.exists():
            try:return json.loads(destination.read_text())
            except json.JSONDecodeError:destination.rename(destination.with_suffix('.interrupted-'+str(int(time.time()))+'.json'))
        schema_path=destination.with_suffix('.schema.json');schema_path.write_text(json.dumps(schema))
        args=['codex','exec','--sandbox','read-only','--ephemeral','--skip-git-repo-check','--disable','shell_tool','--disable','apps','--disable','multi_agent','-c','web_search="disabled"','--output-schema',str(schema_path),'-o',str(destination),'--json']
        for name in self.runner.config.get('mcp_servers',{}):args+=['-c',f'mcp_servers.{name}.enabled=false']
        env={k:v for k,v in os.environ.items() if not any(x in k.upper() for x in ['TOKEN','API_KEY','SERGEY_','TELEGRAM','LINEAR','REWARDS_'])}
        with tempfile.TemporaryDirectory(prefix='owner-preview-planner-') as tmp:
            args+=['-C',tmp,'-'];self.runner.run(args,input=prompt,env=env,timeout=210)
        destination.chmod(0o600);return json.loads(destination.read_text())

    def implement(self,job):
        self.guard(job);p=self.pilot;work=self.source_folder;revision=p['revision'];base=p['base_head']
        if p['branch']!='preview/'+p['draft_id'] or not re.fullmatch('[a-f0-9]{32}',p['draft_id']):raise DeliveryBlocked('preview_branch_scope_violation')
        if not work.exists():self.command(['git','worktree','add','-b',p['branch'],str(work),base],cwd=ROOT)
        if self.git(work,'branch','--show-current')!=p['branch']:raise DeliveryBlocked('preview_branch_changed')
        current=self.git(work,'rev-parse','HEAD')
        if current!=base and not self.git(work,'status','--porcelain') and not self.state.operation(job['id'],'focused'):
            if subprocess.run(['git','merge-base','--is-ancestor',current,base],cwd=work,capture_output=True).returncode==0:self.git(work,'merge','--ff-only',base)
        receipt=self.state.operation(job['id'],'implementation')
        if receipt:return receipt['body']
        plan_file=self.folder/f'plan-r{revision}.json'
        if not plan_file.exists():
            catalog=[]
            for path in self.git(work,'ls-files').splitlines():
                if allowed(path):
                    text=(work/path).read_text();symbols=[f'{i}: {line[:100]}' for i,line in enumerate(text.splitlines(),1) if re.match(r'^(def |class |async def |@router)|<h[1-3]|id="',line.strip())][:35]
                    catalog.append({'path':path,'lines':len(text.splitlines()),'symbols':symbols})
            obj=lambda props,req=None:{'type':'object','additionalProperties':False,'properties':props,'required':req or list(props)}
            selection_schema=obj({'ranges':{'type':'array','minItems':1,'maxItems':10,'items':obj({'path':{'type':'string'},'start':{'type':'integer'},'end':{'type':'integer'}})}})
            selected=self.model('Read-only product planner, no tools. Select up to ten relevant code ranges (max 250 lines each), based only on the confirmed task. No secrets/process/updater/data/schema/auth files.\n'+json.dumps({'task':p['description'],'catalog':catalog},ensure_ascii=False),selection_schema,self.folder/f'select-r{revision}.json')
            snippets=[]
            for part in selected['ranges']:
                if not allowed(part['path']):raise DeliveryBlocked('selection_outside_scope')
                lines=(work/part['path']).read_text().splitlines();start=max(1,part['start']);end=min(len(lines),part['end'])
                if not start<=end or end-start>250:raise DeliveryBlocked('selection_range_invalid')
                snippets.append({'path':part['path'],'start':start,'text':'\n'.join(lines[start-1:end])})
            edit=obj({'path':{'type':'string'},'old':{'type':'string'},'new':{'type':'string'}})
            action=obj({'role':{'type':'string','enum':['link','button','textbox','searchbox']},'name':{'type':'string'},'action':{'type':'string','enum':['click','fill']},'value':{'type':'string'}})
            schema=obj({'edits':{'type':'array','minItems':1,'maxItems':12,'items':edit},'tier':{'type':'string','enum':['T1','T2','T3','T4']},'reason':{'type':'string'},'tests':{'type':'array','maxItems':3,'items':{'type':'string'}},'browser_path':{'type':'string'},'browser_actions':{'type':'array','maxItems':8,'items':action},'expect_text':{'type':'string'}})
            plan=self.model('Read-only delivery planner. Return minimal exact old/new replacements, based on the full confirmed task and these code snippets. No tools/commands. No protected files, no persistence/auth/SQL/filesystem/network changes. Do not fabricate missing code: if the task cannot safely fit T1/T2 choose T3/T4 and explain. Choose existing focused unittest modules only, no release/Windows/full suite. For web changes supply browser route, concrete normal role actions and observable expected text. No browser actions on shared Railway: these run on synthetic TEMP only.\n'+json.dumps({'task':p['description'],'snippets':snippets},ensure_ascii=False),schema,plan_file)
        else:plan=json.loads(plan_file.read_text())
        head=self.git(work,'rev-parse','HEAD')
        if head!=base and not self.git(work,'status','--porcelain') and not self.state.operation(job['id'],'focused'):
            ancestor=subprocess.run(['git','merge-base','--is-ancestor',head,base],cwd=work,capture_output=True)
            if ancestor.returncode==0:self.git(work,'merge','--ff-only',base);head=base
        base_texts={}
        for edit in plan['edits']:
            if not allowed(edit['path']):raise DeliveryBlocked('protected_or_invalid_product_path')
            probe=subprocess.run(['git','show',base+':'+edit['path']],cwd=work,capture_output=True,text=True)
            base_texts[edit['path']]=probe.stdout if probe.returncode==0 else None
        expected,diff,actual_tier=proposed_files(work,plan['edits'],base_texts)
        if head==base:
            prior=self.git(work,'diff',self.config['accepted_base_head'],base)
            schema={'type':'object','additionalProperties':False,'properties':{'tier':{'type':'string','enum':['T1','T2','T3','T4']},'within_task':{'type':'boolean'},'protected':{'type':'boolean'},'reason':{'type':'string'}},'required':['tier','within_task','protected','reason']}
            review=self.model('Independent read-only risk review. Check actual entire cumulative task diff and dependencies, contract boundaries and frozen. Protected data/auth/SQL/updater/filesystem/network/security => T4. Cross-flow/uncertain => T3. T1/T2 only for genuinely narrow local changes.\n'+json.dumps({'task':p['description'],'prior_unaccepted_diff':prior,'diff':diff,'prior_tier':p['tier']},ensure_ascii=False),schema,self.folder/f'risk-r{revision}.json')
            if review['protected'] or not review['within_task'] or max(review['tier'],plan['tier'],actual_tier) not in {'T1','T2'}:raise DeliveryBlocked('actual_diff_requires_owner_decision')
            for path,content in expected.items():
                target=work/path;current=target.read_text() if target.exists() else None
                if current not in {base_texts[path],content}:raise DeliveryBlocked('preview_partial_edit_conflict')
                target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content)
            changed=self.git(work,'diff','--name-only',base).splitlines();untracked=self.git(work,'ls-files','--others','--exclude-standard').splitlines()
            if set(changed+untracked)!=set(expected):raise DeliveryBlocked('actual_diff_files_changed')
            self.git(work,'diff','--check')
            self.focused(work,plan,expected)
            self.state.operation(job['id'],'focused','done',{'files':{p:hashlib.sha256(t.encode()).hexdigest() for p,t in expected.items()}})
            self.guard(job);self.git(work,'add','--',*expected);self.git(work,'commit','-m',f"feat({p['issue_id']}): Owner preview r{revision}")
            head=self.git(work,'rev-parse','HEAD')
        elif self.git(work,'rev-parse','HEAD^')!=base:raise DeliveryBlocked('preview_commit_ancestry_changed')
        if not self.state.operation(job['id'],'focused'):raise DeliveryBlocked('focused_receipt_missing')
        for path,text in expected.items():
            if (work/path).read_text()!=text:raise DeliveryBlocked('recovered_product_diff_conflict')
        if self.git(work,'status','--porcelain'):raise DeliveryBlocked('preview_tree_not_clean')
        self.guard(job)
        remote=self.git(work,'ls-remote','origin','refs/heads/'+p['branch'])
        if not remote or remote.split()[0]!=head:self.git(work,'push','origin','HEAD:refs/heads/'+p['branch'])
        docs=[e['path'] for e in plan['edits'] if e['path'].endswith('.md')]
        preview_path=plan['browser_path'] or ('/static/owner-preview-docs/'+urllib.parse.quote(docs[0],safe='/')+'.txt' if docs else '/legacy?tab=about')
        result={'source_head':head,'worktree':str(work),'url':self.config['origin'],'preview_path':preview_path,'actual_tier':plan['tier'],'focused':'static + selected TEMP checks + browser where applicable'}
        self.state.operation(job['id'],'implementation','sent',result);return result

    def focused(self,work,plan,files):
        python=self.config['test_python']
        for path,text in files.items():
            if path.endswith('.py'):ast.parse(text)
            elif path.endswith('.html'):self.command([python,'-c','from jinja2 import Environment;from pathlib import Path;import sys;Environment().parse(Path(sys.argv[1]).read_text())',str(work/path)])
            elif path.endswith('.js'):self.command(['node','--check',str(work/path)])
            elif path.endswith('.css') and text.count('{')!=text.count('}'):raise DeliveryBlocked('css_braces_invalid')
        for test in plan['tests']:
            if not re.fullmatch(r'tests\.test_[a-zA-Z0-9_]+',test) or re.search(r'updat|recover|release|packag|windows|daily|sergey',test,re.I):raise DeliveryBlocked('focused_test_outside_scope')
            if not (work/(test.replace('.','/')+'.py')).is_file():raise DeliveryBlocked('focused_test_missing')
        if any(not p.endswith('.md') for p in files) and not plan['browser_path']:raise DeliveryBlocked('browser_check_required')
        self.command([python,str(ROOT/'scripts/sergey_preview_checks.py'),'--worktree',str(work),'--plan',str(self.folder/f"plan-r{self.pilot['revision']}.json"),'--node-module',self.config['playwright_module'],'--dependency-dir',self.config.get('dependency_dir','')],timeout=180)

    def package(self,job,body):
        staging=super().package(job,body)
        work=Path(body['worktree'])
        for name in self.git(work,'ls-tree','-r','--name-only',body['source_head']).splitlines():
            if name.endswith('.md') and allowed(name):
                target=staging/'backend/app/static/owner-preview-docs'/(name+'.txt');target.parent.mkdir(parents=True,exist_ok=True)
                target.write_text(self.command(['git','show',body['source_head']+':'+name],cwd=work))
        identity=staging/'delivery_identity.json';metadata=json.loads(identity.read_text())
        metadata['files']={p.relative_to(staging).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((staging/'backend').rglob('*')) if p.is_file()}
        identity.write_text(json.dumps(metadata,sort_keys=True));return staging

    def fingerprint(self):
        """Temporary per-probe SSH key; fixed preview target, accepted host trust, no long-lived key."""
        service=self.status();self.config['ssh_user']=service['id']
        folder=self.folder/'access';folder.mkdir(exist_ok=True,mode=0o700);key=folder/'temporary-key'
        if not key.exists():self.command(['ssh-keygen','-q','-t','ed25519','-N','','-C','ALE528-preview-'+self.pilot['draft_id'],'-f',str(key)])
        key.chmod(0o600)
        fingerprint=self.command(['ssh-keygen','-lf',str(key)+'.pub']).split()[1]
        discovered=Path.home()/'.ssh'/('ale528-owner-preview-'+self.pilot['draft_id'])
        for original,destination in [(key,discovered),(key.with_suffix('.pub'),discovered.with_suffix('.pub'))]:
            if destination.exists() and destination.read_bytes()!=original.read_bytes():raise DeliveryBlocked('temporary_ssh_key_name_collision')
            shutil.copyfile(original,destination);destination.chmod(0o600)
        proof=folder/'access.json';proof.write_text(json.dumps({'fingerprint':fingerprint,'local_key':str(discovered),'closed':False}));proof.chmod(0o600)
        # Reconcile our own registration only; no changes to any unrelated keys.
        try:
            listed=self.railway(['ssh','keys','list'])
            if fingerprint not in listed:self.railway(['ssh','keys','add','--key',fingerprint,'--name','ALE-528 Owner preview '+self.pilot['draft_id'][:8]])
            output=self.command(['ssh','-T','-i',str(key),'-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+self.config['ssh_known_hosts'],'-o','ConnectTimeout=10',service['id']+'@ssh.railway.com',shlex.join(['python','-c',FINGERPRINT.replace('MEDIA_MODE',repr(media_check_mode(self.config,self.pilot)))])],timeout=60)
            for line in reversed(output.splitlines()):
                if line.startswith('{'):return json.loads(line)
            raise DeliveryBlocked('preview_fingerprint_missing')
        finally:
            cleanup=subprocess.run([shutil.which('railway') or '/opt/homebrew/bin/railway','ssh','keys','remove',fingerprint],cwd=self.config['linked_directory'],capture_output=True,timeout=40)
            if cleanup.returncode:raise DeliveryBlocked('railway_temporary_access_cleanup_required')
            for path in [key,key.with_suffix('.pub'),discovered,discovered.with_suffix('.pub')]:path.unlink(missing_ok=True)
            proof.write_text(json.dumps({'fingerprint':fingerprint,'closed':True}))

    def verify(self,job):
        self.guard(job);body=json.loads(job['body']);before=self.state.operation(job['id'],'before')['body'];after=self.fingerprint()
        for key in ['sqlite_snapshot','counts','media_check_scope','media_count','media_sha256','signing_state','auth_state']:
            if before[key]!=after[key]:raise DeliveryBlocked('preview_data_or_auth_changed')
        status,raw=self.http('/preview/identity');identity=json.loads(raw)
        if (status!=200 or identity.get('source_head')!=body['source_head'] or not after.get('code_matches_manifest') or identity.get('delivery_issue')!=self.pilot['issue_id'] or identity.get('contract_revision')!=self.pilot['revision']):raise DeliveryBlocked('preview_identity_mismatch')
        if self.http('/health',False)[0]!=401 or self.http('/updates/check')[0]!=404:raise DeliveryBlocked('preview_auth_or_updater_guard_changed')
        self.state.operation(job['id'],'verification','sent',{'before':before,'after':after})
        return {'deployed_head':body['source_head'],'data_preserved':True,'url':self.config['origin']}
