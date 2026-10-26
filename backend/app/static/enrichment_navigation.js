/* Resume only the enrichment workspace; every other top-level destination stays intact. */
(() => {
  const BASE = '/data-maintenance/enrichment/biographies', KEY = 'fedorinov:enrichment-workspace:v5';
  function update() {
    let state; try { state = JSON.parse(sessionStorage.getItem(KEY) || '{}'); } catch (_) { state = {}; }
    const valid = /^[a-f0-9]{64}$/.test(state.token || '') && Date.now() - state.savedAt < 7 * 86400000;
    document.querySelectorAll('[data-maintenance-nav]').forEach(link => { link.href = valid ? BASE + '/preview/' + state.token : '/data-maintenance'; });
  }
  document.addEventListener('click', event => {
    const link=event.target.closest?.('[data-maintenance-nav]');
    if(!link||event.button||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;
    update();
    if(link.pathname!=='/data-maintenance'){event.preventDefault();location.assign(link.href);}
  }, true);
  document.addEventListener('DOMContentLoaded',update,{once:true});
  update(); window.addEventListener('pageshow', update); window.addEventListener('enrichment-resume-change', update);
})();
