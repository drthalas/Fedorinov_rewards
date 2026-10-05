(function () {
  const button = document.querySelector('[data-summary-booklets]');
  if (!button) return;
  const panel = document.getElementById('summary-booklets-progress');
  const progress = panel.querySelector('progress');
  const label = panel.querySelector('[role="status"]');
  const save = document.getElementById('summary-booklets-save-form');
  const empty = button.dataset.total === '0';
  let busy = false;

  async function request(url, options) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(url, {...options, signal: controller.signal});
      if (!response.ok) throw new Error((await response.text()).trim() || 'Не удалось сформировать буклеты.');
      return await response.json();
    } finally { clearTimeout(timeout); }
  }

  function show(job) {
    panel.hidden = false;
    progress.value = job.percent;
    label.textContent = `${job.completed} из ${job.total} · ${job.percent}%`;
    if (job.state === 'ready') {
      label.textContent += ' — PDF готов.';
      save.action = `/summary/booklets/${job.id}/file`;
      save.hidden = false;
    } else if (job.state === 'failed') {
      throw new Error(job.error);
    } else if (job.completed === job.total) {
      label.textContent += ' — Сборка общего PDF…';
    }
  }

  async function follow(job) {
    busy = true;
    button.disabled = true;
    save.hidden = true;
    try {
      while (true) {
        show(job);
        if (job.state !== 'running') break;
        await new Promise(resolve => setTimeout(resolve, 500));
        job = await request(`/summary/booklets/${job.id}`);
      }
    } finally {
      busy = false;
      button.disabled = empty;
    }
  }

  function failed(error) {
    panel.hidden = false;
    label.textContent = error.name === 'AbortError'
      ? 'Не удалось получить прогресс. Нажмите «Сформировать буклет», чтобы проверить текущее формирование.'
      : (error.message || 'Не удалось получить прогресс. Повторите попытку.');
  }

  button.addEventListener('click', async function () {
    if (busy || empty) return;
    busy = true;
    button.disabled = true;
    save.hidden = true;
    panel.hidden = false;
    progress.value = 0;
    label.textContent = 'Подготовка буклетов…';
    try {
      const body = new FormData();
      body.set('snapshot', button.dataset.summaryBooklets);
      await follow(await request('/summary/booklets', {method: 'POST', body}));
    } catch (error) { failed(error); }
    finally { busy = false; button.disabled = empty; }
  });

  // Resume progress when returning to the matrix while this runtime is still working.
  busy = true;
  button.disabled = true;
  request('/summary/booklets/active').then(job => job ? follow(job) : null)
    .catch(failed).finally(() => { busy = false; button.disabled = empty; });
})();
