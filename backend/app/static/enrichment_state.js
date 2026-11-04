(() => {
  'use strict';
  const BASE='/data-maintenance/enrichment/biographies', KEY='fedorinov:enrichment-workspace:v5';
  const page=document.querySelector('[data-bio-level="biographies"]'); if(!page)return;
  let state={}; try{state=JSON.parse(sessionStorage.getItem(KEY)||'{}');}catch(_){}
  if(!state || Date.now()-(state.savedAt||0)>7*86400000)state={};
  const panel=document.getElementById('bio-manual-dialog'),content=panel.querySelector('[data-manual-content]');
  let replacing=false, busy=false, invalid=false;
  const ws=()=>document.querySelector('[data-bio-workspace]');
  const operations=()=>[];
  const position=()=>({page:document.querySelector('.page')?.scrollTop||0,window:scrollY,list:document.querySelector('[data-bucket-panel]:not([hidden]) [data-review-list]')?.scrollTop||0});
  function restore(p){if(!p)return;const main=document.querySelector('.page');if(main)main.scrollTop=p.page;window.scrollTo(0,p.window||0);const list=document.querySelector('[data-bucket-panel]:not([hidden]) [data-review-list]');if(list)list.scrollTop=p.list||0;}
  function clear(){invalid=true;state={};try{sessionStorage.removeItem(KEY);}catch(_){}window.dispatchEvent(new Event('enrichment-resume-change'));}
  function remember(){
    if(replacing||invalid||!ws()||ws().dataset.fatal==='true'&&!state.prepare)return;
    state.openBiographies=[...document.querySelectorAll('[data-person-bio][open]')].map(d=>d.dataset.personBio);state.token=ws().dataset.token;state.filename=ws().dataset.filename;state.savedAt=Date.now();
    if(panel.hidden)state.scroll=position();else state.panelScroll=position();
    const form=content.querySelector('[data-manual-plan]');
    if(form&&state.active?.row){state.drafts||={};state.drafts[state.active.row]={revision:form.querySelector('[name=review_revision]').value,values:Object.fromEntries(new FormData(form))};}
    try{sessionStorage.setItem(KEY,JSON.stringify(state));}catch(_){}
    window.dispatchEvent(new Event('enrichment-resume-change'));
  }
  function paginate(){
    const key=state.bucket||'ready';let active;
    document.querySelectorAll('[data-bucket]').forEach(b=>{const selected=b.dataset.bucket===key;b.setAttribute('aria-selected',String(selected));b.tabIndex=selected?0:-1;});
    document.querySelectorAll('[data-bucket-panel]').forEach(p=>{p.hidden=p.dataset.bucketPanel!==key;if(!p.hidden)active=p;});
    if(!active)return;
    const rows=[...active.querySelectorAll('[data-review-row]')],pages=Math.max(1,Math.ceil(rows.length/50));
    state.page=Math.max(1,Math.min(state.page||1,pages));
    rows.forEach((r,i)=>r.hidden=i<(state.page-1)*50||i>=state.page*50);
    const nav=active.querySelector('[data-pagination]');nav.hidden=rows.length<=50;
    nav.querySelector('[data-page-range]').textContent=`Показаны ${(state.page-1)*50+1}–${Math.min(state.page*50,rows.length)} из ${rows.length}`;
    nav.querySelector('[data-page-current]').textContent=`Страница ${state.page} из ${pages}`;
    nav.querySelectorAll('[data-page-first],[data-page-prev]').forEach(b=>b.disabled=state.page===1);
    nav.querySelectorAll('[data-page-next],[data-page-last]').forEach(b=>b.disabled=state.page===pages);
  }
  function choices(){
    const form=content.querySelector('[data-manual-plan]');if(!form)return;
    const identity=form.querySelector('[name=identity_choice]:checked')?.value;
    const fields=form.querySelector('[data-identity-fields]');if(fields)fields.hidden=!!form.querySelector('[data-identity-question]')&&identity!=='same';
    const rejected=form.querySelector('[data-identity-rejected]');if(rejected)rejected.hidden=identity!=='different';
    form.querySelector('[data-review-save]').disabled=!(identity||form.querySelector('[name$="_choice"]:checked'));
    form.querySelectorAll('[data-review-field]').forEach(f=>f.querySelector('[data-review-reset]').hidden=!f.querySelector('input:checked'));
  }
  async function html(url,options={}){
    const r=await fetch(url,{credentials:'same-origin',cache:'no-store',...options});
    const type=r.headers.get('content-type')||'';
    if(type.includes('text/html'))return [r,await r.text()];
    const data=await r.json();const p=document.createElement('p');p.setAttribute('role','alert');p.textContent=data.detail||'Не удалось проверить данные.';return [r,p.outerHTML];
  }
  async function refresh(){
    const data=new FormData();data.set('operations',JSON.stringify(operations()));
    const [response,text]=await html(BASE+'/workspace/'+state.token,{method:'POST',body:data});
    if(!response.ok){clear();throw new Error('Карточки или принятые решения изменились. Выберите свежий файл; ничего не записано.');}
    const t=document.createElement('template');t.innerHTML=text;const next=t.content.firstElementChild;next.hidden=!panel.hidden;ws().replaceWith(next);paginate();
    if(next.dataset.fatal==='true')clear();
  }
  async function open(url,row=null,restoring=false){
    if(!new URL(url,location.origin).pathname.startsWith(BASE+'/'))return;
    if(!restoring)remember();state.active={url,row};panel.hidden=false;ws().hidden=true;page.classList.add('bio-detail-open');
    content.textContent='Открываем данные…';
    try{
      const [r,text]=await html(url);content.innerHTML=text;
      if(!r.ok){clear();return;}
      const form=content.querySelector('[data-manual-plan]'),draft=state.drafts?.[row];
      if(form&&draft){
        if(form.querySelector('[name=review_revision]').value===draft.revision)form.querySelectorAll('input[type=radio]').forEach(radio=>radio.checked=draft.values[radio.name]===radio.value);
        else{delete state.drafts[row];delete(state.stages||{})[row];}
      }
      choices();content.querySelector('h2')?.focus({preventScroll:true});
      if(restoring)restore(state.panelScroll);else panel.scrollIntoView({block:'start'});
      remember();
    }catch(_){content.textContent='Не удалось открыть данные. Вернитесь к списку и повторите попытку.';}
  }
  function close(){remember();if(state.prepare){state.prepare.mode='list';prepEpoch++;}busy=false;state.active=null;panel.hidden=true;ws().hidden=false;page.classList.remove('bio-detail-open');paginate();restore(state.scroll);remember();}
  function error(message){const p=document.createElement('p');p.setAttribute('role','alert');p.className='notice notice-error';p.textContent=message;content.prepend(p);}
  document.addEventListener('click',event=>{
    const t=event.target;if(!(t instanceof Element))return;
    const person=t.closest('[data-person-leave]');if(person){state.person=person.dataset.personLeave;remember();}
    const tab=t.closest('[data-bucket]');if(tab){remember();state.bucket=tab.dataset.bucket;state.page=1;paginate();remember();return;}
    const pageButton=t.closest('[data-page-first],[data-page-prev],[data-page-next],[data-page-last]');
    if(pageButton){const total=document.querySelector(`[data-bucket-panel="${state.bucket||'ready'}"]`).querySelectorAll('[data-review-row]').length;state.page=pageButton.hasAttribute('data-page-first')?1:pageButton.hasAttribute('data-page-last')?Math.ceil(total/50):(state.page||1)+(pageButton.hasAttribute('data-page-next')?1:-1);paginate();ws().scrollIntoView({block:'start'});remember();return;}
    const button=t.closest('[data-manual-open]');if(button){void open(button.dataset.manualOpen,button.dataset.manualPerson);return;}
    const history=t.closest('[data-review-history]');if(history){void open(history.dataset.reviewHistory,state.active?.row);return;}
    if(t.closest('[data-manual-close],[data-manual-undo]')){close();return;}
    const reset=t.closest('[data-review-reset]');if(reset){reset.closest('fieldset').querySelectorAll('input').forEach(r=>r.checked=false);reset.dispatchEvent(new Event('change',{bubbles:true}));}
  });
  document.addEventListener('keydown',event=>{
    const tab=event.target.closest?.('[data-bucket]');if(tab&&['ArrowRight','ArrowLeft','Home','End'].includes(event.key)){event.preventDefault();const tabs=[...document.querySelectorAll('[data-bucket]')];const i=tabs.indexOf(tab),n=event.key==='Home'?0:event.key==='End'?tabs.length-1:(i+(event.key==='ArrowRight'?1:tabs.length-1))%tabs.length;tabs[n].click();tabs[n].focus();}
    if(event.key==='Escape'&&!panel.hidden&&!busy)close();
  });
  document.addEventListener('change',event=>{
    if(event.target.closest('[data-manual-plan]')){if(state.active?.row)delete(state.stages||{})[state.active.row];choices();remember();}
  });
  const previewRegion=document.querySelector('[data-import-preview]'),operationRegion=document.querySelector('[data-import-operation]');
  let monitoring=false;
  const initialCompleted=JSON.parse(operationRegion.querySelector('[data-import-initial]').textContent||'null');
  function operationScreen(kind){
    previewRegion.hidden=true;panel.hidden=true;page.classList.remove('bio-detail-open');operationRegion.hidden=false;
    ['progress','success','failure'].forEach(name=>operationRegion.querySelector('[data-import-'+name+']').hidden=name!==kind);
  }
  function importing(item={}){
    operationScreen('progress');state.importMode='importing';state.active=null;busy=true;
    operationRegion.querySelector('[data-import-phase]').textContent=item.phase||'Импортируем данные…';
    const done=item.done||0,total=item.total||state.importTotal||0,percent=Math.min(99,item.percent||0);
    operationRegion.querySelector('[data-import-progress-bar]').value=percent;
    operationRegion.querySelector('[data-import-processed]').textContent=`Обработано: ${done} / ${total}`;
    operationRegion.querySelector('[data-import-percent]').textContent=percent+'%';remember();
  }
  function imported(value,noChanges=false,already=false,allStale=false){
    operationScreen('success');state.importMode='success';state.active=null;busy=false;
    if(state.importOperation){
      // Only confirmed commit reaches here. Keep the durable identity, release
      // preview DOM and drafts; unfinished/failure/reconnect paths are untouched.
      state={token:state.token,filename:state.filename,importOperation:state.importOperation,importMode:'success'};
      ws().replaceChildren();ws().dataset.terminal='true';ws().hidden=true;
      content.replaceChildren();prepEpoch++;
    }
    previewRegion.hidden=false;
    operationRegion.querySelector('[data-import-success] h2').textContent=allStale?'Все карточки пропущены':noChanges?'Изменений нет':'Импорт завершён';
    for(const name of ['saved','biographies','years','names','skipped','stale_skipped'])operationRegion.querySelector('[data-result-'+name.replace('_','-')+']').textContent=value[name]||0;
    let notice=operationRegion.querySelector('[data-import-already]');if(!notice){notice=document.createElement('p');notice.dataset.importAlready='';operationRegion.querySelector('[data-import-success] h2').after(notice);}
    notice.textContent=already?'Этот файл уже импортирован. Новая запись не выполнялась.':'';
    const skipped=operationRegion.querySelector('[data-import-skips]'),list=skipped.querySelector('ul');list.replaceChildren();
    // Detailed skipped rows remain in the explicit full report, not this summary.
    skipped.hidden=!list.childElementCount;remember();window.dispatchEvent(new Event('enrichment-import-completed'));
  }
  function importFailure(item){
    operationScreen('failure');busy=false;state.importMode='failure';
    operationRegion.querySelector('[data-import-failure-text]').textContent=item.error||'Статус временно недоступен. Проверьте его снова; импорт повторно не запускается.';
    operationRegion.querySelector('[data-import-failure-list]').hidden=!['failed','interrupted'].includes(item.state);remember();
  }
  async function operationStatus(){
    const r=await fetch(BASE+'/import/operations/'+state.importOperation,{cache:'no-store'});const data=await r.json();
    if(!r.ok)throw new Error(data.detail||'Статус временно недоступен.');return data;
  }
  async function monitorImport(){
    if(monitoring)return;monitoring=true;let failures=0;
    try{while(true){
      let item;try{item=await operationStatus();failures=0;}catch(e){if(++failures>=3){importFailure({error:e.message});return;}await new Promise(r=>setTimeout(r,300*failures));continue;}
      if(item.state==='succeeded'){imported(item.result);return;}
      if(['failed','interrupted','unknown'].includes(item.state)){importFailure(item);return;}
      importing(item);await new Promise(r=>setTimeout(r,200));
    }}finally{monitoring=false;}
  }
  async function startImport(form){
    if(busy)return;remember();delete state.prepare;prepEpoch++;state.importListScroll=state.scroll;state.importOperation=form.querySelector('[name=operation]').value;state.importTotal=Number(form.dataset.importTotal);state.importMode='importing';
    importing();operationRegion.scrollIntoView({block:'start'});
    try{const r=await fetch(form.action,{method:'POST',body:new FormData(form),credentials:'same-origin'});const item=await r.json();
      if(!r.ok){importFailure({state:'failed',error:item.detail||'Не удалось начать импорт. Ничего не подтверждено.'});return;}
      if(item.state==='succeeded')imported(item.result);else await monitorImport();
    }catch(_){await monitorImport();}
  }
  async function importList(){
    state.importMode='list';state.active=null;busy=false;
    try{await refresh();operationRegion.hidden=true;previewRegion.hidden=false;panel.hidden=true;ws().hidden=false;page.classList.remove('bio-detail-open');
      document.querySelector('[data-upload-status]').textContent='Результаты загруженного файла.';paginate();restore(state.importListScroll||state.scroll);remember();
    }catch(e){importFailure({state:'failed',error:e.message});}
  }
  operationRegion.querySelector('[data-import-list]').addEventListener('click',event=>{event.preventDefault();location.assign(BASE+'/preview/'+state.token+'?details=true');});
  operationRegion.querySelector('[data-import-failure-list]').addEventListener('click',()=>void importList());
  operationRegion.querySelector('[data-import-status-retry]').addEventListener('click',()=>{importing();void monitorImport();});
  // Preparation has its own durable request identity. Losing a response never
  // changes that identity or implies that the server worker stopped.
  let prepEpoch=0;
  const prepareVisible=p=>state.prepare===p&&p.mode!=='list'&&!panel.hidden;
  function preparing(p){
    previewRegion.hidden=false;operationRegion.hidden=true;panel.hidden=false;ws().hidden=true;page.classList.add('bio-detail-open');
    content.replaceChildren(document.querySelector('[data-prepare-template]').content.cloneNode(true));
    state.active=null;p.mode='preparing';busy=true;remember();
  }
  function prepareProgress(item){
    const root=content.querySelector('[data-prepare-screen]');if(!root)return;
    root.querySelector('[data-prepare-phase]').textContent=item.phase||'Ожидаем начала проверки…';
    const bar=root.querySelector('progress'),measurable=Number.isFinite(item.total)&&item.total>0;
    if(measurable)bar.value=Math.min(99,item.percent||0);else bar.removeAttribute('value');
    root.querySelector('[data-prepare-count]').textContent=measurable?`Обработано: ${item.done||0} / ${item.total} · этап ${Math.min(99,item.percent||0)}%`:'Объём этого этапа заранее неизвестен.';
    root.querySelector('[data-prepare-connection]').hidden=true;
  }
  function prepareFailure(p,message,known=false){
    if(!prepareVisible(p))return;
    const root=content.querySelector('[data-prepare-screen]');if(!root)return;
    busy=false;p.mode=known?'failed':'unknown';
    root.querySelector('[data-prepare-heading]').textContent=known?'Подготовка не завершена':'Состояние подготовки не подтверждено';
    root.querySelector('[data-prepare-meter]').hidden=true;
    root.querySelector('[data-prepare-error]').textContent=message;
    root.querySelector('[data-prepare-status-retry]').hidden=known;
    root.querySelector('[data-prepare-retry]').hidden=!known;remember();
  }
  async function prepareRequest(url,options={}){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
    try{
      const response=await fetch(url,{cache:'no-store',credentials:'same-origin',...options,signal:controller.signal});
      const payload=await response.json();return {response,payload};
    }finally{clearTimeout(timer);}
  }
  async function monitorPrepare(p){
    const epoch=++prepEpoch;let failures=0;
    while(prepareVisible(p)&&epoch===prepEpoch){
      try{
        let response,payload;
        if(!p.job){
          const data=new FormData();data.set('revision',p.revision);data.set('request_id',p.request);
          ({response,payload}=await prepareRequest(BASE+'/workspace/'+p.token+'/prepare',{method:'POST',body:data}));
          if(!prepareVisible(p)||epoch!==prepEpoch)return;
          if(!response.ok){prepareFailure(p,payload.detail||'Не удалось начать проверку. Ничего не записано. Повторите проверку.',true);return;}
          p.job=payload.job;remember();
        }else{
          ({response,payload}=await prepareRequest(BASE+'/prepare/operations/'+p.job));
          if(!prepareVisible(p)||epoch!==prepEpoch)return;
          if(!response.ok)throw new Error('status');
        }
        if(payload.state==='succeeded'){
          const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
          let result,text;
          try{result=await fetch(BASE+'/prepare/operations/'+p.job+'/result',{cache:'no-store',signal:controller.signal});text=await result.text();}finally{clearTimeout(timer);}
          if(!prepareVisible(p)||epoch!==prepEpoch)return;
          if(!result.ok){prepareFailure(p,'Сводка подготовки недоступна. Данные не записывались. Повторите проверку файла.',true);return;}
          content.innerHTML=text;busy=false;p.mode='ready';remember();content.querySelector('h2')?.focus({preventScroll:true});return;
        }
        if(['failed','interrupted','unknown'].includes(payload.state)){
          prepareFailure(p,payload.error||'Подготовка недоступна. Ничего не записано. Повторите проверку файла.',true);return;
        }
        failures=0;prepareProgress(payload);
        await new Promise(r=>setTimeout(r,500));
      }catch(_){
        if(!prepareVisible(p)||epoch!==prepEpoch)return;
        const notice=content.querySelector('[data-prepare-connection]');if(notice){notice.hidden=false;notice.textContent='Связь прервана, проверяем состояние… Сервер может продолжать подготовку. Данные ещё не сохраняются.';}
        if(++failures>=3){prepareFailure(p,'Связь с сервером недоступна. Неизвестно, завершилась ли подготовка. Проверьте статус после восстановления связи; повторная работа и запись не запускаются.');return;}
        await new Promise(r=>setTimeout(r,1000*failures));
      }
    }
  }
  function beginPrepare(form,retry=false){
    if(busy)return;remember();
    if(retry||!state.prepare){state.prepare={token:state.token,revision:form.querySelector('[name=revision]').value,request:crypto.randomUUID().replaceAll('-','')};}
    const p=state.prepare;preparing(p);panel.scrollIntoView({block:'start'});void monitorPrepare(p);
  }
  document.addEventListener('click',event=>{
    if(event.target.closest('[data-prepare-status-retry]')&&state.prepare){preparing(state.prepare);void monitorPrepare(state.prepare);}
    if(event.target.closest('[data-prepare-retry]'))beginPrepare(ws().querySelector('[data-import-plan]'),true);
  });
  document.addEventListener('submit',async event=>{
    const form=event.target;if(!form.matches('[data-manual-plan],[data-import-plan],[data-manual-commit]'))return;
    event.preventDefault();if(form.matches('[data-import-plan]')){beginPrepare(form);return;}if(form.matches('[data-import-start]')){void startImport(form);return;}if(busy)return;busy=true;remember();
    const prior=[...content.childNodes],data=new FormData(form),row=state.active?.row;
    const button=form.querySelector('[type=submit]');button.disabled=true;
    try{
      const [r,text]=await html(form.action,{method:'POST',body:data});content.innerHTML=text;
      if(!r.ok){const failure=content.textContent;if(r.status===409){clear();ws().querySelector('[data-import-plan] button').disabled=true;}else{content.replaceChildren(...prior);content.querySelectorAll('[role=alert]').forEach(e=>e.remove());error(failure);}return;}
      if(content.querySelector('[data-no-import]')){await refresh();return;}
      const staged=content.querySelector('[data-staged-operation]');
      if(staged){state.stages||={};state.stages[staged.dataset.row]=staged.dataset.stagedOperation;await refresh();close();return;}
      if(content.querySelector('[data-manual-result]')){state.stages={};state.drafts={};state.active=null;await refresh();close();const target=ws().querySelector('[data-review-list-result]');target.textContent='Импорт завершён. Сохранены только подтверждённые изменения.';target.hidden=false;}
      else{const op=content.querySelector('[name=operation]')?.value;if(op)state.active={url:BASE+'/confirm/'+op,row:null};panel.scrollIntoView({block:'start'});remember();}
    }catch(e){content.replaceChildren(...prior);error(e.message||'Связь прервана. Повтор этого же подтверждения не создаёт повторную запись.');}
    finally{busy=false;button.disabled=false;}
  });
  document.querySelectorAll('[data-auto-preview] input[type=file]').forEach(input=>input.addEventListener('change',()=>{
    const form=input.form;if(!form.querySelector('[name=file]').files.length)return;
    if(Object.keys(state.stages||{}).length&&!confirm('Выбрать другой файл и убрать подготовленные решения? Подготовленные решения ещё не записаны.')){input.value='';return;}
    replacing=true;clear();document.querySelector('[data-upload-status]').textContent='Проверяем файл…';form.requestSubmit();
  }));
  window.addEventListener('pagehide',remember);
  window.addEventListener('pageshow',event=>{if(event.persisted&&ws()){let current={};try{current=JSON.parse(sessionStorage.getItem(KEY)||'{}');}catch(_){}if(current.token!==state.token){location.replace(current.token?BASE+'/preview/'+current.token:BASE+'?new=1');return;}if(state.importOperation&&state.importMode==='success'){location.reload();return;}if(state.importOperation&&state.importMode!=='list'){importing();void monitorImport();return;}if(state.prepare&&state.prepare.mode!=='list'){preparing(state.prepare);void monitorPrepare(state.prepare);return;}void refresh().then(()=>{if(state.active)return open(state.active.url,state.active.row,true);}).catch(e=>{clear();error(e.message);});}});
  async function initialize(){
    if(new URL(location.href).searchParams.has('new'))clear();
    if(!ws()){
      // Empty file/failure placeholders carry role=alert while hidden. Only a
      // real server error invalidates the stored workspace on the entry page.
      if(page.hasAttribute('data-resume-error'))return;
      if(page.querySelector('.notice-error[role=alert]:not([hidden])'))clear();
      else if(/^[a-f0-9]{64}$/.test(state.token||''))location.replace(BASE+'/preview/'+state.token);
      return;
    }
    if(ws().dataset.fatal==='true'&&!state.prepare){clear();return;}
    invalid=false;if(state.token!==ws().dataset.token)state={};state.token=ws().dataset.token;
    const details=new URL(location.href).searchParams.has('details');
    history.replaceState(null,'',BASE+'/preview/'+state.token+(details?'?details=true':''));
    if(initialCompleted&&!details){
      state.importOperation=initialCompleted.operation;imported(initialCompleted.summary,initialCompleted.no_changes,initialCompleted.already_done,initialCompleted.all_stale);return;
    }
    if(details){state.importMode='list';}
    if(state.importOperation&&state.importMode!=='list'){importing();void monitorImport();return;}
    if(state.prepare&&state.prepare.mode!=='list'){paginate();preparing(state.prepare);void monitorPrepare(state.prepare);return;}
    if(initialCompleted&&state.importMode==='list'){previewRegion.hidden=false;operationRegion.hidden=true;document.querySelector('[data-upload-status]').textContent='Результаты загруженного файла.';}
    try{if(operations().length)await refresh();paginate();document.querySelectorAll('[data-person-bio]').forEach(d=>d.open=(state.openBiographies||[]).includes(d.dataset.personBio));if(state.active)await open(state.active.url,state.active.row,true);else restore(state.scroll);remember();}
    catch(e){clear();error(e.message);}
  }
  void initialize();
})();
