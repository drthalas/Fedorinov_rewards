(function () {
  function initialize(config) {
    const button = document.querySelector(config.selector);
    if (!button) return;
    const panel = document.getElementById(config.prefix + '-progress');
    const progress = panel.querySelector('progress');
    const label = panel.querySelector('[role="status"]');
    const controls = panel.querySelector('.summary-booklets-controls');
    const stop = panel.querySelector('[data-booklets-stop]');
    const pause = panel.querySelector('[data-booklets-pause]');
    const save = document.getElementById(config.prefix + '-save-form');
    const saved = document.getElementById(config.prefix + '-save-status');
    const empty = (config.form ? document.querySelector('[data-summary-booklets]') : button).dataset.total === '0';
    let busy = false;
    let current = null;
    let controlling = false;
    let revision = 0;
    const active = job => ['running', 'pausing', 'paused', 'stopping'].includes(job.state);

    async function request(url, options) {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 15000);
      try {
        const response = await fetch(url, {...options, signal: controller.signal});
        if (!response.ok) throw new Error((await response.text()).trim() || 'Не удалось сформировать буклеты.');
        return await response.json();
      } finally { clearTimeout(timeout); }
    }

    function clearSaved() {
      save.hidden = true;
      saved.replaceChildren();
      saved.hidden = true;
      saved.classList.remove('notice-success', 'notice-error');
    }

    function show(job) {
      current = job;
      if (job.state === 'stopped') {
        panel.hidden = true;
        clearSaved();
        return;
      }
      panel.hidden = false;
      progress.value = job.percent;
      label.textContent = `${job.completed} из ${job.total} · ${job.percent}%`;
      controls.hidden = !active(job);
      stop.disabled = controlling || job.state === 'stopping';
      pause.disabled = controlling || ['pausing', 'stopping'].includes(job.state);
      const paused = job.state === 'paused';
      pause.textContent = paused ? '▶' : 'Ⅱ';
      pause.setAttribute('aria-label', paused ? 'Продолжить формирование' : 'Приостановить формирование');
      pause.title = pause.getAttribute('aria-label');
      if (job.state === 'ready') {
        save.action = `${config.endpoint}/${job.id}/file`;
        save.hidden = false;
      } else if (job.state === 'failed') {
        throw new Error(job.error);
      }
    }

    async function follow(job) {
      busy = true;
      button.disabled = true;
      clearSaved();
      current = job;
      try {
        while (true) {
          job = current;
          show(job);
          if (!active(job)) break;
          await new Promise(resolve => setTimeout(resolve, 300));
          // Don't let a poll started before a control overwrite that control's result.
          if (controlling) continue;
          const before = revision;
          const next = await request(`${config.endpoint}/${job.id}`);
          if (controlling || before !== revision) continue;
          current = next;
        }
      } finally {
        busy = false;
        button.disabled = empty;
      }
    }

    function failed(error) {
      controls.hidden = true;
      clearSaved();
      panel.hidden = false;
      label.textContent = error.name === 'AbortError'
        ? 'Не удалось получить прогресс. Повторите попытку.'
        : (error.message || 'Не удалось получить прогресс. Повторите попытку.');
    }

    async function control(action) {
      if (!current || controlling || !active(current)) return;
      controlling = true;
      revision += 1;
      stop.disabled = pause.disabled = true;
      try {
        const job = await request(`${config.endpoint}/${current.id}/${action}`, {method: 'POST'});
        controlling = false;
        show(job);
      } catch (error) {
        controlling = false;
        failed(error);
        stop.disabled = pause.disabled = false;
      }
    }
    stop.addEventListener('click', () => control('stop'));
    pause.addEventListener('click', () => control(current.state === 'paused' ? 'resume' : 'pause'));

    (config.form || button).addEventListener(config.form ? 'summary-pdf-generate' : 'click', async function () {
      if (busy || empty) return;
      busy = true;
      button.disabled = true;
      clearSaved();
      controls.hidden = true;
      panel.hidden = false;
      progress.value = 0;
      label.textContent = config.preparation;
      try {
        const body = config.form ? new FormData(config.form) : new FormData();
        if (!config.form) body.set('snapshot', button.dataset.summaryBooklets);
        await follow(await request(config.endpoint, {method: 'POST', body}));
      } catch (error) { failed(error); }
      finally { busy = false; button.disabled = empty; }
    });

    busy = true;
    button.disabled = true;
    request(config.endpoint + '/active').then(job => job ? follow(job) : null)
      .catch(failed).finally(() => { busy = false; button.disabled = empty; });
  }
  initialize({selector: '[data-summary-booklets]', prefix: 'summary-booklets', endpoint: '/summary/booklets', preparation: 'Подготовка буклетов…'});
  const form = document.querySelector('[data-summary-pdf-job]');
  if (form) initialize({selector: '[data-summary-pdf-options-open]', prefix: 'summary-pdf-job', endpoint: '/summary/pdf-jobs', preparation: 'Подготовка PDF…', form});
})();
