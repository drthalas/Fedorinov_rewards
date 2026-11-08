"""ALE-528 exact-artifact production pilot. No general release queue or rebuild path."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
import urllib.request

try:
    from .sergey_delivery import DeliveryBlocked, DeliveryStore, contract_hash, private_json
    from .sergey_intake import Store, Linear, ApiError
    from . import publish_github_release as publisher
    from . import send_release_notification as sender
except ImportError:
    from sergey_delivery import DeliveryBlocked, DeliveryStore, contract_hash, private_json
    from sergey_intake import Store, Linear, ApiError
    import publish_github_release as publisher
    import send_release_notification as sender

REPO = 'drthalas/Fedorinov_rewards'
STAGES = ('merge', 'tag', 'record', 'archive', 'manifest', 'publish', 'parity',
          'notify_primary', 'notify_copy', 'close_issue')
SAFE_REPLAY = {'merge', 'tag', 'archive', 'manifest', 'publish', 'close_issue'}


class ReadRetry(RuntimeError):
    pass


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def controls(store):
    return (store.meta('paused') != '1' and store.meta('delivery_paused') != '1'
            and store.meta('delivery_cancel:ALE-533') != '1')


def arm(store, owner, binding):
    key = fingerprint(binding)
    with store.transaction():
        previous = json.loads(store.meta('production_approval', 'null'))
        if previous and previous['fingerprint'] == key:
            return previous
        record = dict(fingerprint=key, binding=binding, owner_id=owner, token=secrets.token_hex(12),
                      state='waiting', created=time.time(), expires=time.time()+86400,
                      outbox_key='production-approval:'+key)
        store.set_meta('production_approval', json.dumps(record))
        store.set_meta('production_status','READY FOR OWNER PRODUCTION APPROVAL: 2.0.33')
        store.enqueue(record['outbox_key'], 'telegram', {
            'chat_id':owner,
            'text':('Настоящий публичный выпуск 2.0.33 — ALE-533 revision 2.\n'
                    'Изменение: уточнена рекомендация о резервных копиях в «О программе».\n'
                    f"Принятый product HEAD: {binding['source_head']}\n"
                    f"Package HEAD: {binding['package_head']}\nSHA256: {binding['zip_sha256']}\n"
                    f"ZIP: {binding['size']} bytes. Product PASS и physical updater PASS 2.0.32 → 2.0.33 сохранены.\n\n"
                    'Нажатие разрешает сервису самостоятельно: controlled merge этой product-линии в main, '
                    'публичный Release 2.0.33 с тем же ZIP и production manifest, анонимную проверку bytes/SHA, '
                    'затем штатные уведомления Сергею и вам через действующий release sender/journal. '
                    'Сергей получит настоящее сообщение о доступном обновлении. Это не тест.\n'
                    'Framework-код не включается. Общая очередь остаётся выключенной. '
                    'При конфликте или неопределённой отправке — остановка с blocker, без слепых повторов.'),
            'reply_markup':{'inline_keyboard':[
                [{'text':'Опубликовать 2.0.33 Сергею','callback_data':'prod:yes:'+record['token']}],
                [{'text':'Отложить','callback_data':'prod:no:'+record['token']}]]}})
        store.event('production_approval_armed', key)
        return record


def callback(store, update, actor, role):
    query=update['callback_query'];parts=query.get('data','').split(':')
    record=json.loads(store.meta('production_approval','null'))
    invalid='Production-кнопка устарела или уже обработана. Повторный выпуск не запускается.'
    if (role!='owner' or not record or actor!=record['owner_id'] or len(parts)!=3
            or parts[1] not in {'yes','no'} or parts[2]!=record['token'] or record['state']!='waiting'
            or not controls(store)):
        return invalid
    if fingerprint(record['binding'])!=record['fingerprint']:return invalid
    row=store.db.execute('SELECT status,result FROM outbox WHERE key=?',(record['outbox_key'],)).fetchone()
    receipt=json.loads(row['result'] or '{}') if row else {}
    if not row or row['status']!='sent' or query['message'].get('message_id')!=receipt.get('message_id'):
        return invalid
    if time.time()>record['expires']:
        record['state']='expired';store.set_meta('production_approval',json.dumps(record));return invalid
    record.update(state='owner_approved' if parts[1]=='yes' else 'deferred',callback_update_id=update['update_id'],
                  callback_id=query['id'],message_id=query['message']['message_id'],approved_at=time.time())
    store.set_meta('production_approval',json.dumps(record))
    store.event('production_'+record['state'],record['fingerprint'])
    return ('Разрешение настоящего выпуска 2.0.33 сохранено. Сервис самостоятельно продолжает '
            'merge → Release/manifest → public parity → уведомления Сергею и Owner. '
            'Общая очередь выключена.') if parts[1]=='yes' else 'Публикация отложена. Main/production не меняются.'


class LiveAdapter:
    def __init__(self, config):
        self.config=config;self.work=Path(config['worktree']);self.root=Path(config['directory'])
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        intake_credentials=private_json(Path(config['intake_credentials']))
        self.owner=int(intake_credentials['SERGEY_INTAKE_OWNER_USER_ID'])
        self.sergey=int(intake_credentials['SERGEY_INTAKE_SERGEY_USER_ID'])
        self.linear=Linear(intake_credentials['SERGEY_INTAKE_LINEAR_API_KEY'],{})
        standard=sender.daily.read_env_file(Path(config['notification_config']))
        primary,copies=sender.daily.resolve_recipients(standard)
        if primary!=self.sergey or copies!=[self.owner] or primary==self.owner:
            raise DeliveryBlocked('standard_notification_recipient_identity_conflict')
        self.token=sender.daily.resolve_token(standard)
        self.journal=Path(config['notification_journal'])
        self.recipients={'primary':primary,'copy':self.owner}

    def command(self,args,*,binary=False,not_found=False):
        try:
            r=subprocess.run(args,cwd=self.work,capture_output=True,timeout=60)
        except (OSError,subprocess.TimeoutExpired):
            raise ReadRetry('transport_unavailable') from None
        if r.returncode:
            if not_found and b'HTTP 404' in r.stderr:return None
            diagnostic=(r.stderr+r.stdout).lower()
            if any(code in diagnostic for code in [b'gh006',b'gh013',b'protected branch',b'repository rule violations']):
                raise DeliveryBlocked('main_branch_policy_rejected')
            if b'host key verification failed' in diagnostic:
                raise DeliveryBlocked('git_host_identity_verification_failed')
            raise ReadRetry('remote_command_failed')
        return r.stdout if binary else r.stdout.decode().strip()

    def git(self,*args):return self.command(['git',*args])
    def gh(self,*args,**kwargs):return self.command(['gh',*args,'--repo',REPO],**kwargs)
    def api(self,path,*,binary=False,not_found=False):
        args=['gh','api',f'repos/{REPO}/'+path]
        if binary:args+=['-H','Accept: application/octet-stream']
        raw=self.command(args,binary=binary,not_found=not_found)
        return raw if binary or raw is None else json.loads(raw)
    def refs(self):
        lines=self.git('ls-remote','origin','refs/heads/main','refs/tags/v2.0.33','refs/tags/v2.0.33^{}').splitlines()
        return {line.split()[1]:line.split()[0] for line in lines}
    def release(self):return self.api('releases/tags/v2.0.33',not_found=True)

    def local(self,b):
        if self.config.get('general_queue') is not False or self.config.get('version')!='2.0.33':
            raise DeliveryBlocked('production_pilot_config_invalid')
        if (sha(self.config['artifact'])!=b['zip_sha256'] or Path(self.config['artifact']).stat().st_size!=b['size']
                or sha(self.config['manifest'])!=b['manifest_sha256'] or sha(self.config['evidence'])!=b['updater_pass_sha256']):
            raise DeliveryBlocked('approved_artifact_or_gate_changed')
        if self.git('rev-parse','HEAD')!=b['package_head'] or self.git('status','--porcelain'):
            raise DeliveryBlocked('product_worktree_changed')
        if self.git('rev-parse',b['package_head']+'^{tree}')!=b['package_tree']:
            raise DeliveryBlocked('package_tree_changed')
        if self.git('remote','get-url','origin') not in {'git@github.com:'+REPO+'.git','https://github.com/'+REPO+'.git'}:
            raise DeliveryBlocked('product_remote_conflict')
        if (self.sender_identity()!=b['notification_sender_sha256']
                or sha(self.config['notification_config'])!=b['notification_config_sha256']
                or fingerprint(str(self.journal.resolve()))!=b['notification_journal_identity']):
            raise DeliveryBlocked('standard_notification_identity_changed')
        if (self.root/'release-notes.md').read_text()!=self.notes(b):
            raise DeliveryBlocked('production_release_notes_changed')

    def notes(self,b):
        manifest=json.loads(Path(self.config['manifest']).read_text())
        return '# Награды и награждённые v2.0.33\n\n'+'\n'.join('- '+n for n in manifest['notes'])+'\n\nALE-528 artifact '+fingerprint(b)+'\n'

    def sender_identity(self):
        return fingerprint({'roles':self.recipients,'token_sha256':hashlib.sha256(self.token.encode()).hexdigest()})

    def scope(self,b):
        try:data=self.linear.call('query{framework:issue(id:"ALE-528"){description state{type}} product:issue(id:"ALE-533"){description state{type}}}',{})
        except ApiError:raise ReadRetry('linear_read_unavailable') from None
        if (contract_hash(data['framework']['description'])!=b['framework_scope_hash']
                or contract_hash(data['product']['description'])!=b['issue_scope_hash']):
            raise DeliveryBlocked('production_linear_scope_changed')
        if (data['framework']['state']['type'] in {'canceled','completed'}
                or data['product']['state']['type']=='canceled'):
            raise DeliveryBlocked('production_issue_cancelled_or_parent_closed')

    def baseline(self,b,merge_started=False,publish_started=False):
        refs=self.refs();main=refs.get('refs/heads/main');tag=refs.get('refs/tags/v2.0.33^{}',refs.get('refs/tags/v2.0.33'))
        if main!=b['expected_main'] and not (merge_started and main==b['package_head']):
            raise DeliveryBlocked('production_main_shifted')
        if tag and tag!=b['package_head']:raise DeliveryBlocked('production_tag_conflict')
        latest=self.api('releases/latest')
        if latest['id']!=b['previous_release_id'] and not (publish_started and latest['tag_name']=='v2.0.33'):
            raise DeliveryBlocked('production_latest_shifted')

    def prepare(self):
        e=private_json(Path(self.config['evidence']));m=e['manifest'];head=e['package_head']
        if (e['result']!='OWNER PHYSICAL UPDATER PILOT PASS' or e['issue']!='ALE-533' or e['revision']!=2
                or m['version']!='2.0.33' or not e['post']['installed_file_parity'] or e['post']['updater_status']!='success'):
            raise DeliveryBlocked('physical_gate_receipt_missing')
        if (m['candidate_commit']!=head or m['accepted_product_head']!=e['source_head']
                or e['post']['target_version']!=m['version'] or e['post']['real_test_writes']
                or Path(self.config['artifact']).name!=m['filename'] or Path(self.config['manifest']).name!='latest.json'):
            raise DeliveryBlocked('physical_gate_artifact_identity_conflict')
        if self.git('remote','get-url','origin') not in {'git@github.com:'+REPO+'.git','https://github.com/'+REPO+'.git'}:
            raise DeliveryBlocked('product_remote_conflict')
        self.git('merge-base','--is-ancestor',e['source_head'],head)
        self.git('merge-base','--is-ancestor',self.config['expected_main'],head)
        delta=self.git('diff','--name-only',e['source_head'],head).splitlines()
        if delta!=['backend/app/version.py','release_notes/2.0.33.md']:
            raise DeliveryBlocked('unexpected_candidate_version_delta')
        combined=self.git('diff','--name-only',self.config['expected_main'],head).splitlines()
        if combined!=['backend/app/templates/legacy.html','backend/app/version.py','release_notes/2.0.33.md']:
            raise DeliveryBlocked('unexpected_product_line_delta')
        if any('sergey_' in name for name in self.git('ls-tree','-r','--name-only',head).splitlines()):
            raise DeliveryBlocked('framework_in_product_tree')
        data=self.linear.call('query{framework:issue(id:"ALE-528"){description} product:issue(id:"ALE-533"){description}}',{})
        if not data['framework']['description'].startswith('## ACTIVE — подключить production publication к боту'):
            raise DeliveryBlocked('production_scope_not_active')
        if e['source_head'] not in data['product']['description'].split('\n---\n')[0]:
            raise DeliveryBlocked('accepted_product_source_not_in_owner_pass')
        states=self.linear.call('query{team(id:"cc0f1982-1457-48af-967b-d56a672ee8ae"){states{nodes{id type}}}}',{})
        completed=[s['id'] for s in states['team']['states']['nodes'] if s['type']=='completed']
        if len(completed)!=1:raise DeliveryBlocked('linear_completed_state_ambiguous')
        latest=self.api('releases/latest');refs=self.refs()
        if refs.get('refs/heads/main')!=self.config['expected_main'] or latest['tag_name']!='v2.0.32':
            raise DeliveryBlocked('production_baseline_shifted')
        existing=self.release()
        if existing or refs.get('refs/tags/v2.0.33'):raise DeliveryBlocked('version_already_reserved_reconcile_required')
        public_manifest=json.loads(Path(self.config['manifest']).read_text())
        url=f'https://github.com/{REPO}/releases/download/v2.0.33/'+m['filename']
        if (public_manifest['version']!='2.0.33' or public_manifest['sha256']!=m['sha256']
                or public_manifest['download_url']!=url):raise DeliveryBlocked('public_manifest_identity_conflict')
        b=dict(issue='ALE-533',revision=2,version='2.0.33',source_head=e['source_head'],package_head=head,
               package_tree=self.git('rev-parse',head+'^{tree}'),zip_sha256=m['sha256'],size=m['size'],filename=m['filename'],
               manifest_sha256=sha(self.config['manifest']),updater_pass_sha256=sha(self.config['evidence']),
               expected_main=self.config['expected_main'],previous_release_id=latest['id'],
               framework_scope_hash=contract_hash(data['framework']['description']),
               issue_scope_hash=contract_hash(data['product']['description']),completed_state_id=completed[0],
               notification_sender_sha256=self.sender_identity(),
               notification_config_sha256=sha(self.config['notification_config']),
               notification_journal_identity=fingerprint(str(self.journal.resolve())))
        (self.root/'release-notes.md').write_text(self.notes(b))
        self.local(b)
        self.scope(b)
        message=sender.build_message('2.0.33',self.config['manifest'],str(self.work/'release_notes/2.0.33.md'))
        for role,recipient in self.recipients.items():
            record=sender.delivery_record(self.journal,'2.0.33',role,recipient,message)
            if record:raise DeliveryBlocked('production_notification_history_requires_reconcile')
        return b

    def asset(self,release,name,checksum,size=None):
        assets=[a for a in release['assets'] if a['name']==name]
        if not assets:return None
        if len(assets)!=1:raise DeliveryBlocked('duplicate_release_asset')
        a=assets[0]
        if size is not None and a['size']!=size:raise DeliveryBlocked('release_asset_size_conflict')
        content=self.api('releases/assets/'+str(a['id']),binary=True)
        if hashlib.sha256(content).hexdigest()!=checksum:raise DeliveryBlocked('release_asset_sha_conflict')
        return {'asset_id':a['id'],'sha256':checksum,'size':len(content)}

    def reconcile(self,stage,b):
        if stage=='merge':
            main=self.refs().get('refs/heads/main')
            if main==b['package_head']:return {'head':main,'tree':b['package_tree']}
            if main!=b['expected_main']:raise DeliveryBlocked('production_main_shifted')
            return None
        if stage=='tag':
            refs=self.refs();tag=refs.get('refs/tags/v2.0.33^{}',refs.get('refs/tags/v2.0.33'))
            if tag and tag!=b['package_head']:raise DeliveryBlocked('production_tag_conflict')
            return {'head':tag} if tag else None
        if stage.startswith('notify_'):
            role=stage.removeprefix('notify_');message=sender.build_message('2.0.33',self.config['manifest'],str(self.work/'release_notes/2.0.33.md'))
            record=sender.delivery_record(self.journal,'2.0.33',role,self.recipients[role],message)
            if record and record['status']!='sent':raise DeliveryBlocked('notification_'+role+'_uncertain_no_retry')
            return record
        if stage=='close_issue':
            try:issue=self.linear.call('query{issue(id:"ALE-533"){state{type}}}',{})['issue']
            except ApiError:raise ReadRetry('linear_read_unavailable') from None
            return {'completed':True} if issue['state']['type']=='completed' else None
        if stage=='parity':
            def anonymous(url):
                try:
                    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'ALE528-public-parity'}),timeout=30) as r:return r.read()
                except Exception:raise ReadRetry('anonymous_download_pending') from None
            raw=anonymous(f'https://github.com/{REPO}/releases/latest/download/latest.json')
            if raw!=Path(self.config['manifest']).read_bytes():raise ReadRetry('public_manifest_parity_pending')
            m=json.loads(raw);archive=anonymous(m['download_url'])
            if archive!=Path(self.config['artifact']).read_bytes() or hashlib.sha256(archive).hexdigest()!=b['zip_sha256']:
                raise DeliveryBlocked('public_archive_parity_failed')
            return {'anonymous':True,'sha256':b['zip_sha256'],'bytes':len(archive),'manifest_sha256':b['manifest_sha256']}
        release=self.release()
        if not release:
            if stage!='record':raise DeliveryBlocked('production_release_record_missing')
            return None
        if release['tag_name']!='v2.0.33':raise DeliveryBlocked('release_version_conflict')
        if release['draft'] and ('ALE-528 artifact '+fingerprint(b)) not in (release.get('body') or ''):
            raise DeliveryBlocked('foreign_draft_release')
        if stage=='record':
            return {'release_id':release['id'],'url':release['html_url'],'draft':release['draft']}
        if stage=='archive':return self.asset(release,b['filename'],b['zip_sha256'],b['size'])
        if stage=='manifest':return self.asset(release,'latest.json',b['manifest_sha256'],Path(self.config['manifest']).stat().st_size)
        if stage=='publish':
            if release['prerelease']:raise DeliveryBlocked('release_channel_conflict')
            if release['draft']:return None
            latest=self.api('releases/latest')
            if latest['id']!=release['id']:raise DeliveryBlocked('published_release_not_latest')
            return {'release_id':release['id'],'url':release['html_url'],'stable':True}
        raise DeliveryBlocked('unknown_production_stage')

    def execute(self,stage,b):
        if stage=='merge':
            # Exact CAS plus proved ancestry: this update is a fast-forward, never a history rewrite.
            self.git('push','--porcelain','--force-with-lease=refs/heads/main:'+b['expected_main'],
                     'origin',b['package_head']+':refs/heads/main')
        elif stage=='tag':self.git('push','origin',b['package_head']+':refs/tags/v2.0.33')
        elif stage=='record':self.gh(*publisher.staged_release_command('2.0.33',self.root/'release-notes.md'))
        elif stage in {'archive','manifest'}:
            release=self.release()
            if not release or not release['draft'] or ('ALE-528 artifact '+fingerprint(b)) not in (release.get('body') or ''):
                raise DeliveryBlocked('release_not_owned_draft_for_upload')
            path=Path(self.config['artifact'] if stage=='archive' else self.config['manifest'])
            self.gh(*publisher.staged_upload_command('2.0.33',path))
        elif stage=='publish':
            release=self.release()
            if not release or not release['draft'] or ('ALE-528 artifact '+fingerprint(b)) not in (release.get('body') or ''):
                raise DeliveryBlocked('release_not_owned_draft_for_publish')
            if (not self.asset(release,b['filename'],b['zip_sha256'],b['size'])
                    or not self.asset(release,'latest.json',b['manifest_sha256'])):
                raise DeliveryBlocked('release_assets_missing_before_stable')
            self.gh(*publisher.staged_publish_command('2.0.33'))
        elif stage.startswith('notify_'):
            role=stage.removeprefix('notify_');message=sender.build_message('2.0.33',self.config['manifest'],str(self.work/'release_notes/2.0.33.md'))
            return sender.send_one_durable('2.0.33',role,self.recipients[role],message,self.token,self.journal,confirmed=True)
        elif stage=='close_issue':
            self.linear.call('mutation($id:String!,$state:String!){issueUpdate(id:$id,input:{stateId:$state}){success}}',
                             {'id':'5f29d200-a8aa-4c44-94b8-812abbb6eaf0','state':b['completed_state_id']})
        else:raise DeliveryBlocked('read_only_stage_not_mutable')


class ProductionRunner:
    """Runs under the existing single delivery service lock and one active pilot slot."""
    def __init__(self,state,intake,adapter,binding):
        self.state=state;self.intake=intake;self.adapter=adapter;self.binding=binding;self.next_tick=0

    def tick(self,job):
        self.intake.set_meta('production_worker_binding',fingerprint(self.binding))
        self.intake.set_meta('production_worker_heartbeat',str(time.time()))
        if not job or not controls(self.intake) or time.time()<self.next_tick:return False
        a=json.loads(self.intake.meta('production_approval','null'));key=fingerprint(self.binding)
        if (not a or a['fingerprint']!=key or fingerprint(a['binding'])!=key
                or a['state']!='owner_approved' or not a.get('callback_update_id')):return False
        op=self.state.operation(job['id'],'production')
        if op and fingerprint(op['body'].get('binding'))!=key:
            self.block(job,op['body'],a,'production_run_binding_conflict');return False
        if op and op['status']=='complete':
            self.complete_report(job,a);return True
        if op and op['status']=='blocked':
            self.block(job,op['body'],a,op['body']['blocker']);return False
        if not op:
            if time.time()>a['expires']:return False
            self.state.operation(job['id'],'production','active',{'stage':0,'binding':self.binding,'approval_update':a['callback_update_id'],'started':time.time()})
        run=self.state.operation(job['id'],'production')['body'];index=run['stage']
        self.intake.set_meta('production_status','2.0.33: '+STAGES[index])
        stage_started=time.time()
        try:
            self.adapter.local(self.binding);self.adapter.scope(self.binding)
            self.adapter.baseline(self.binding,
                merge_started=bool(self.state.operation(job['id'],'prod:merge')),
                publish_started=bool(self.state.operation(job['id'],'prod:publish')))
            stage=STAGES[index];kind='prod:'+stage;step=self.state.operation(job['id'],kind)
            receipt=self.adapter.reconcile(stage,self.binding)
            if receipt is None:
                if stage=='parity':raise ReadRetry('public_parity_pending')
                if step and stage not in SAFE_REPLAY:
                    raise DeliveryBlocked(stage+'_outcome_uncertain_no_retry')
                if step and step['body'].get('attempt',0)>=3:
                    raise DeliveryBlocked(stage+'_mutation_unresolved')
                self.state.operation(job['id'],kind,'intent',{'at':time.time(),'attempt':(step or {}).get('body',{}).get('attempt',0)+1})
                try:receipt=self.adapter.execute(stage,self.binding)
                except DeliveryBlocked:
                    raise
                except Exception:
                    self.next_tick=time.time()+5
                    self.state.event('production_reconcile_required',stage)
                    return False
                receipt=receipt or self.adapter.reconcile(stage,self.binding)
                if receipt is None:raise ReadRetry('mutation_receipt_pending')
            timing=step['body'] if step else {}
            receipt={**receipt,'intent_at':timing.get('intent_at',timing.get('at',stage_started)),
                     'completed_at':timing.get('completed_at',time.time())}
            self.state.operation(job['id'],kind,'done',receipt)
            run.update(stage=index+1,last_completed=stage,last_completed_at=time.time())
            run.pop('read_retry_since',None)
            if index+1==len(STAGES):
                run['finished']=time.time();run['execution_wall_seconds']=run['finished']-run['started']
                self.state.operation(job['id'],'production','complete',run)
                self.complete_report(job,a)
                return True
            self.state.operation(job['id'],'production','active',run)
            self.intake.set_meta('production_status','2.0.33: '+STAGES[index+1])
        except ReadRetry as error:
            run.setdefault('read_retry_since',time.time());self.next_tick=time.time()+10
            self.state.operation(job['id'],'production','active',run)
            self.intake.set_meta('production_status','2.0.33: awaiting reconcile / '+str(error))
            if time.time()-run['read_retry_since']>600:self.block(job,run,a,'read_reconcile_timeout')
        except Exception as error:
            code=str(error) if re.fullmatch(r'[a-z_]+',str(error)) else 'production_check_failed'
            self.block(job,run,a,code)
        return False

    def complete_report(self,job,a):
        primary=self.state.operation(job['id'],'prod:notify_primary')['body']['message_id']
        copy=self.state.operation(job['id'],'prod:notify_copy')['body']['message_id']
        elapsed=self.state.operation(job['id'],'production')['body'].get('execution_wall_seconds',0)
        self.intake.enqueue('production-complete:'+a['fingerprint'],'telegram',{'chat_id':a['owner_id'],
            'text':f'RELEASE PUBLISHED — OWNER/SERGEY NOTIFIED\n2.0.33\nhttps://github.com/{REPO}/releases/tag/v2.0.33\n'
            f"Package HEAD: {self.binding['package_head']}\nSHA256: {self.binding['zip_sha256']}\n"
            f'Штатный journal: Сергей sent/message_id={primary}; Owner sent/message_id={copy}. '
            f'Public manifest/ZIP anonymous parity PASS. Выполнение публикации: {elapsed:.1f} с wall. '
            'ALE-533 закрыта; ALE-528 Needs Test, общая очередь выключена.'})
        self.intake.set_meta('production_status','RELEASE PUBLISHED — OWNER/SERGEY NOTIFIED')

    def block(self,job,run,a,code):
        run['blocker']=code;self.state.operation(job['id'],'production','blocked',run)
        self.intake.set_meta('production_status','BLOCKED: '+code)
        self.intake.enqueue('production-blocker:'+a['fingerprint']+':'+code,'telegram',{'chat_id':a['owner_id'],
            'text':'Production 2.0.33 остановлена: '+code+'. Уже выполненные этапы сохранены. '
                   'Неизвестные отправки не повторяются; общая очередь выключена.'})


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','arm','status']);p.add_argument('--config',type=Path,required=True)
    args=p.parse_args();os.umask(0o077);cfg=private_json(args.config);intake=Store(Path(cfg['intake_state']))
    try:
        if args.action in {'prepare','arm'}:
            adapter=LiveAdapter(cfg);binding=adapter.prepare()
            if args.action=='arm':
                if cfg.get('binding')!=binding or intake.meta('production_worker_binding')!=fingerprint(binding):
                    raise DeliveryBlocked('production_worker_binding_not_ready')
                if time.time()-float(intake.meta('production_worker_heartbeat','0'))>60:
                    raise DeliveryBlocked('production_worker_heartbeat_stale')
            cfg['binding']=binding
            args.config.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n');args.config.chmod(0o600)
            record=arm(intake,adapter.owner,binding) if args.action=='arm' else None
        else:record=json.loads(intake.meta('production_approval','null'))
        print(json.dumps({'state':record['state'] if record else ('prepared' if args.action=='prepare' else 'not_armed'),'fingerprint':record['fingerprint'] if record else None,
                          'version':record['binding']['version'] if record else cfg.get('version')}))
    finally:intake.db.close()


if __name__=='__main__':main()
