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
    if(replacing||invalid||!ws()||ws().dataset.fatal==='true')return;
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
  function close(){remember();state.active=null;panel.hidden=true;ws().hidden=false;page.classList.remove('bio-detail-open');paginate();restore(state.scroll);remember();}
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
    if(event.key==='Escape'&&!panel.hidden)close();
  });
  document.addEventListener('change',event=>{
    if(event.target.closest('[data-manual-plan]')){if(state.active?.row)delete(state.stages||{})[state.active.row];choices();remember();}
  });
  document.addEventListener('submit',async event=>{
    const form=event.target;if(!form.matches('[data-manual-plan],[data-import-plan],[data-manual-commit]'))return;
    event.preventDefault();if(busy)return;busy=true;remember();
    const prior=[...content.childNodes],data=new FormData(form),row=state.active?.row;
    if(form.matches('[data-import-plan]')){data.set('operations',JSON.stringify(operations()));panel.hidden=false;ws().hidden=true;page.classList.add('bio-detail-open');}
    const button=form.querySelector('[type=submit]');button.disabled=true;
    try{
      const [r,text]=await html(form.action,{method:'POST',body:data});content.innerHTML=text;
      if(!r.ok){const failure=content.textContent;if(r.status===409){clear();ws().querySelector('[data-import-plan] button').disabled=true;}else{content.replaceChildren(...prior);content.querySelectorAll('[role=alert]').forEach(e=>e.remove());error(failure);}return;}
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
  window.addEventListener('pageshow',event=>{if(event.persisted&&ws()){let current={};try{current=JSON.parse(sessionStorage.getItem(KEY)||'{}');}catch(_){}if(current.token!==state.token){location.replace(current.token?BASE+'/preview/'+current.token:BASE+'?new=1');return;}void refresh().then(()=>{if(state.active)return open(state.active.url,state.active.row,true);}).catch(e=>{clear();error(e.message);});}});
  async function initialize(){
    if(new URL(location.href).searchParams.has('new'))clear();
    if(!ws()){
      if(page.querySelector('[role=alert]'))clear();
      else if(/^[a-f0-9]{64}$/.test(state.token||''))location.replace(BASE+'/preview/'+state.token);
      return;
    }
    if(ws().dataset.fatal==='true'){clear();return;}
    invalid=false;if(state.token!==ws().dataset.token)state={};state.token=ws().dataset.token;
    history.replaceState(null,'',BASE+'/preview/'+state.token);
    try{if(operations().length)await refresh();paginate();document.querySelectorAll('[data-person-bio]').forEach(d=>d.open=(state.openBiographies||[]).includes(d.dataset.personBio));if(state.active)await open(state.active.url,state.active.row,true);else restore(state.scroll);remember();}
    catch(e){clear();error(e.message);}
  }
  void initialize();
})();
