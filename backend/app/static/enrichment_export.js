(() => {
  'use strict';
  const BASE='/data-maintenance/enrichment/biographies';
  const block=document.querySelector('[data-export-block]');if(!block)return;
  const form=block.querySelector('form'),button=form.querySelector('[type=submit]'),status=block.querySelector('[data-export-status]');
  const key='fedorinov:enrichment-export:v1';let state={},monitoring=false;
  try{state=JSON.parse(sessionStorage.getItem(key)||'{}');}catch(_){}
  if(!state||Date.now()-(state.savedAt||0)>7*86400000)state={};
  const persist=()=>{state.savedAt=Date.now();try{sessionStorage.setItem(key,JSON.stringify(state));}catch(_){}};
  function render(item){
    status.hidden=false;const running=['queued','running'].includes(item.state);
    button.disabled=running;form.querySelectorAll('select,input').forEach(e=>e.disabled=running);
    block.querySelector('[data-export-phase]').textContent=['failed','interrupted','unknown'].includes(item.state)?'Не удалось подготовить файл':item.state==='disconnected'?'Связь прервана':item.phase||'Подготовка файла не завершена';
    const bar=block.querySelector('[data-export-progress]');bar.hidden=!running&&item.state!=='succeeded';
    if(item.percent==null)bar.removeAttribute('value');else bar.value=item.percent;
    block.querySelector('[data-export-count]').textContent=item.total==null?'':`Обработано: ${item.done} / ${item.total}${item.percent==null?'':' · '+item.percent+'%'}`;
    const error=block.querySelector('[data-export-error]');error.textContent=item.error||'';error.hidden=!item.error;
    block.querySelector('[data-export-ready]').hidden=item.state!=='succeeded';
    const link=block.querySelector('[data-export-download]');link.hidden=item.state!=='succeeded';link.href=BASE+'/export/operations/'+state.operation+'/file';
    block.querySelector('[data-export-reconnect]').hidden=item.state!=='disconnected';
    if(item.state==='disconnected'){button.disabled=true;form.querySelectorAll('select,input').forEach(e=>e.disabled=true);}
  }
  async function monitor(){
    if(monitoring)return;monitoring=true;let failures=0;
    try{while(true){
      let item;try{const r=await fetch(BASE+'/export/operations/'+state.operation,{cache:'no-store'});item=await r.json();if(!r.ok)throw new Error();failures=0;}
      catch(_){if(++failures>=3){render({state:'disconnected',error:'Связь прервана. Проверьте состояние; выгрузка повторно не запускается.'});return;}await new Promise(r=>setTimeout(r,300*failures));continue;}
      render(item);
      if(!['queued','running'].includes(item.state))return;
      await new Promise(r=>setTimeout(r,200));
    }}finally{monitoring=false;}
  }
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(button.disabled||monitoring)return;
    const data=new FormData(form);state={operation:Array.from(crypto.getRandomValues(new Uint8Array(32)),n=>n.toString(16).padStart(2,'0')).join(''),selection:data.get('selection'),limit:data.get('limit')};persist();
    data.set('operation',state.operation);render({state:'queued',phase:'Выбираем записи…'});
    try{const r=await fetch(form.action,{method:'POST',body:data});const item=await r.json();if(!r.ok){render({state:'failed',error:item.detail||'Не удалось начать выгрузку.'});return;}render(item);}
    catch(_){/* Recover status for the same operation, never POST again. */}
    void monitor();
  });
  block.querySelector('[data-export-reconnect]').addEventListener('click',()=>void monitor());
  if(state.operation){form.elements.selection.value=state.selection||'';form.elements.limit.value=state.limit||20;render({state:'queued',phase:'Проверяем состояние выгрузки…'});void monitor();}
  window.addEventListener('pageshow',event=>{if(event.persisted&&state.operation)void monitor();});

  const population=document.querySelector('[data-population]');let updating=false,pendingUpdate=false;
  async function updatePopulation(){
    if(updating){pendingUpdate=true;return;}updating=true;
    const notice=population.querySelector('[data-population-status]');
    try{const r=await fetch(BASE+'/statistics',{cache:'no-store'});if(!r.ok)throw new Error();const data=await r.json();
      for(const name of ['total','filled','empty'])population.querySelector('[data-population-'+name+']').textContent=data[name];notice.hidden=true;
    }catch(_){notice.textContent='Не удалось обновить статистику. Показаны последние полученные значения.';notice.hidden=false;}
    finally{updating=false;if(pendingUpdate){pendingUpdate=false;void updatePopulation();}}
  }
  window.addEventListener('enrichment-import-completed',()=>void updatePopulation());
  window.addEventListener('pageshow',()=>void updatePopulation());
})();
