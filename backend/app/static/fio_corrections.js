(() => {
 'use strict';const root=document.querySelector('[data-fio-corrections]');if(!root)return;
 const BASE=root.dataset.base,KEY='fedorinov:fio-corrections:v1';let state={};try{state=JSON.parse(sessionStorage.getItem(KEY)||'{}');}catch(_){}
 const audit=root.querySelector('[data-fio-audit]'),apply=root.querySelector('[data-fio-apply]'),status=root.querySelector('[data-fio-status]'),bar=root.querySelector('progress'),error=root.querySelector('[data-fio-error]'),result=root.querySelector('[data-fio-result]'),preview=root.querySelector('[data-fio-preview]');
 let busy=false;
 const save=()=>{try{sessionStorage.setItem(KEY,JSON.stringify(state));}catch(_){}};
 const buttons=()=>{audit.disabled=busy;apply.disabled=busy||!state.audit_token||!state.safe;};
 async function request(url,options){const r=await fetch(url,{cache:'no-store',credentials:'same-origin',...options});if(!r.ok){let d;try{d=await r.json();}catch(_){}const e=new Error(d?.detail||'Не удалось получить результат.');e.status=r.status;throw e;}return r;}
 async function showPreview(token,url){preview.innerHTML=await(await request(url||BASE+'/preview/'+token)).text();}
 function progress(item){
  status.hidden=false;root.querySelector('[data-fio-phase]').textContent=item.phase;
  if(item.total||item.state==='succeeded')bar.value=item.percent;else bar.removeAttribute('value');
  root.querySelector('[data-fio-count]').textContent=item.total||item.state==='succeeded'?`Обработано: ${item.done||0} / ${item.total||0}`:'Количество уточняется';
  root.querySelector('[data-fio-percent]').textContent=item.total||item.state==='succeeded'?`${item.percent||0}%`:'—';
  root.querySelector('[data-fio-eta]').textContent=item.eta==null?'Оцениваем время':`Осталось примерно ${Math.ceil(item.eta)} с`;
 }
 async function monitor(pending){
  let failures=0;
  while(true){
   let item;
   try{item=await(await request(BASE+'/jobs/'+pending.job_id)).json();failures=0;}catch(e){if(++failures>=3)throw e;await new Promise(r=>setTimeout(r,300*failures));continue;}
   progress(item);
   if(item.state==='succeeded'){
    if(pending.kind==='audit'){state.audit_token=item.result.audit_token;state.safe=item.result.safe_records;state.skipped=item.result.skipped;await showPreview(state.audit_token);result.textContent=`Проверено всех кавалеров: ${item.result.checked}. Безопасных записей: ${state.safe}.`;}
    else{state.audit_token=null;state.safe=0;const heading=document.createElement('h2');heading.textContent='Исправление завершено';const counts=document.createElement('p');counts.textContent=`Исправлено записей: ${item.result.records}. Исправлено букв: ${item.result.characters}.`+(Number.isInteger(state.skipped)?` Неоднозначных пропусков: ${state.skipped}.`:'');result.replaceChildren(heading,counts);}
    result.hidden=false;state.pending=null;save();return;
   }
   if(['failed','interrupted'].includes(item.state)){state.pending=null;state.audit_token=null;state.safe=0;save();throw new Error(item.error||'Операция не завершена. Повторите аудит.');}
   await new Promise(r=>setTimeout(r,200));
  }
 }
 async function start(kind,resume=false){
  if(busy)return;busy=true;buttons();error.hidden=true;if(!resume)result.hidden=true;
  try{
   if(!resume){state.pending={kind,request_id:crypto.randomUUID(),audit_token:kind==='apply'?state.audit_token:null};save();status.hidden=false;root.querySelector('[data-fio-phase]').textContent='Подготовка';bar.removeAttribute('value');}
   const p=state.pending;if(!p)return;
   if(!p.job_id){const body=new FormData();body.set('kind',p.kind);body.set('request_id',p.request_id);if(p.audit_token)body.set('audit_token',p.audit_token);const item=await(await request(BASE+'/jobs',{method:'POST',body})).json();p.job_id=item.job_id;save();}
   await monitor(p);
  }catch(e){if(e.status&&e.status<500&&!state.pending?.job_id){state.pending=null;state.audit_token=null;state.safe=0;save();}error.textContent=e.message+(state.pending?' Обновите страницу для восстановления известного статуса; повторная запись не запускается.':'');error.hidden=false;}
  finally{busy=!!state.pending;buttons();}
 }
 audit.addEventListener('click',()=>void start('audit'));apply.addEventListener('click',()=>void start('apply'));
 preview.addEventListener('click',e=>{const link=e.target.closest('[data-fio-page]');if(link){e.preventDefault();void showPreview(state.audit_token,link.href).catch(e=>{error.textContent=e.message;error.hidden=false;});}});
 if(state.pending)void start(state.pending.kind,true);
 else if(state.audit_token)void showPreview(state.audit_token).then(buttons).catch(()=>{state={};save();buttons();});else buttons();
})();
