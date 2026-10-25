/* Scoped to data maintenance. Never changes the Cavaliers screen or its routes. */
(() => {
  "use strict";
  const BASE = "/data-maintenance/enrichment/biographies";
  const KEY = "fedorinov:enrichment-workspace:v3";
  const page = document.querySelector("[data-bio-level]");
  if (!page || page.dataset.bioLevel !== "biographies") return;
  let state = {};
  try { state = JSON.parse(sessionStorage.getItem(KEY) || "{}"); } catch (_) { /* Optional browser storage. */ }
  if (!state || typeof state !== "object" || Date.now() - (state.savedAt || 0) > 7 * 86400000) state = {};
  const panel = document.getElementById("bio-manual-dialog");
  const content = panel.querySelector("[data-manual-content]");
  const workspace = () => document.querySelector("[data-bio-workspace]");
  const scroll = () => ({ page: document.querySelector(".page")?.scrollTop || 0, window: scrollY, list: document.querySelector("[data-review-list]")?.scrollTop || 0 });
  const restoreScroll = (value) => {
    if (!value) return;
    const main = document.querySelector(".page"), list = document.querySelector("[data-review-list]");
    if (main) main.scrollTop = value.page || 0;
    if (list) list.scrollTop = value.list || 0;
    window.scrollTo(0, value.window || 0);
  };
  const allowed = (url) => { try { const u = new URL(url, location.origin); return u.origin === location.origin && u.pathname.startsWith(BASE + "/"); } catch (_) { return false; } };
  let draft = null;
  function remember() {
    const ws = workspace();
    if (ws) { state.token = ws.dataset.token; state.filename = ws.dataset.filename; }
    state.filter = document.querySelector("[data-review-filter]")?.value || state.filter || "all";
    if (panel.hidden) state.listScroll = scroll();
    else state.panelScroll = scroll();
    const form = content.querySelector("[data-manual-plan]");
    if (!panel.hidden && form && state.active?.row) {
      state.drafts ||= {};
      state.drafts[state.active.row] = {
        revision: form.querySelector("[name=review_revision]").value,
        values: Object.fromEntries(new FormData(form).entries()),
        fields: Object.fromEntries([...form.querySelectorAll("[data-review-field]")].map((field) => [field.dataset.reviewField, { current: field.dataset.current, proposed: field.dataset.proposed }])),
      };
    }
    state.savedAt = Date.now();
    try { sessionStorage.setItem(KEY, JSON.stringify(state)); } catch (_) { /* Navigation still has a stable GET URL. */ }
  }
  function announce(message) {
    const target = document.querySelector("[data-review-list-result]");
    if (target) { target.textContent = message; target.hidden = false; }
  }
  function filterRows() {
    const select = document.querySelector("[data-review-filter]");
    if (!select) return;
    const value = select.value;
    let ready = 0, postponed = 0;
    document.querySelectorAll("[data-review-row]").forEach((row) => {
      const skipped = (state.skipped || []).includes(row.dataset.reviewRow) && row.dataset.state !== "confirmed";
      row.classList.toggle("review-postponed", skipped);
      const status = row.querySelector(".import-status"), reason = row.querySelector("[data-manual-row-status]");
      if (status) { status.dataset.originalText ||= status.textContent; status.textContent = skipped ? "Отложено" : status.dataset.originalText; }
      if (reason) { reason.dataset.originalText ||= reason.textContent; reason.textContent = skipped ? "Не войдёт в общий импорт. Откройте кавалера снова, чтобы вернуть его в работу." : reason.dataset.originalText; }
      if (skipped) postponed++;
      if (row.dataset.auto === "true" && !skipped) ready++;
      row.hidden = !(value === "all" || value === "ready" && row.dataset.auto === "true" && !skipped || value === "confirmed" && row.dataset.state === "confirmed" || value === "pending" && (["manual", "blocked"].includes(row.dataset.state) || skipped));
    });
    const count = document.querySelector("[data-import-ready-count]"); if (count) count.textContent = ready;
    const postponedCount = document.querySelector("[data-postponed-count]"); if (postponedCount) { postponedCount.textContent = "Отложено: " + postponed; postponedCount.hidden = !postponed; }
    const form = document.querySelector("[data-import-plan]");
    if (form) { form.querySelector("[name=exclude]").value = JSON.stringify(state.skipped || []); form.querySelector("button[type=submit]").disabled = !ready; }
  }
  function updateChoices() {
    const form = content.querySelector("[data-manual-plan]");
    if (!form) return;
    form.querySelector("[data-review-save]").disabled = !(Number(form.dataset.autoCount) || form.querySelector("input[type=radio]:checked"));
    form.querySelectorAll("[data-review-field]").forEach((field) => { field.querySelector("[data-review-reset]").hidden = !field.querySelector("input:checked"); });
  }
  function restoreChoices() {
    const form = content.querySelector("[data-manual-plan]"), saved = state.drafts?.[state.active?.row];
    if (!form || !saved) return;
    const sameOptions = [...form.querySelectorAll("[data-review-field]")].every((field) => saved.fields?.[field.dataset.reviewField]?.current === field.dataset.current && saved.fields?.[field.dataset.reviewField]?.proposed === field.dataset.proposed);
    // A successful server render has already validated the receipt chain. Own
    // imports can change another field without invalidating this pending choice.
    if (form.querySelector("[name=review_revision]").value !== saved.revision && !sameOptions) {
      delete state.drafts[state.active.row];
      const warning = document.createElement("p"); warning.setAttribute("role", "status");
      warning.textContent = "Данные изменились за время отсутствия. Проверьте оставшиеся варианты заново."; content.prepend(warning);
    } else {
      form.querySelectorAll("input[type=radio]").forEach((radio) => { radio.checked = saved.values[radio.name] === radio.value; });
    }
    updateChoices();
  }
  async function fragment(url, options) {
    const response = await fetch(url, { ...options, credentials: "same-origin", cache: "no-store" });
    let html;
    if (response.headers.get("content-type")?.includes("text/html")) html = await response.text();
    else { const body = await response.json(); const error = document.createElement("p"); error.setAttribute("role", "alert"); error.textContent = body.detail || "Проверку не удалось открыть."; html = error.outerHTML; }
    content.innerHTML = html;
    if (!content.querySelector("h2")) { const h = document.createElement("h2"); h.id = "bio-manual-title"; h.tabIndex = -1; h.textContent = "Проверка данных"; content.prepend(h); }
    content.querySelector("h2").focus({ preventScroll: true });
    updateChoices();
    return response;
  }
  async function open(url, row = null, restoring = false) {
    if (!allowed(url)) return;
    if (!restoring) remember();
    state.active = { url, row };
    panel.hidden = false;
    page.classList.add("bio-detail-open");
    if (workspace()) workspace().hidden = true;
    draft = null;
    content.textContent = "Открываем проверку…";
    try { await fragment(url); restoreChoices(); }
    catch (_) { content.textContent = "Не удалось открыть проверку. Вернитесь к списку и повторите попытку."; }
    if (restoring) restoreScroll(state.panelScroll);
    else panel.scrollIntoView({ block: "start" });
    remember();
  }
  function close() {
    remember();
    const row = state.active?.row;
    panel.hidden = true; if (workspace()) workspace().hidden = false;
    page.classList.remove("bio-detail-open");
    state.active = null; draft = null;
    restoreScroll(state.listScroll);
    const button = document.querySelector(`[data-manual-person="${Number(row)}"]`);
    const fallback = document.querySelector(`[data-review-row="${Number(row)}"]`) || workspace()?.querySelector("h2");
    if (button) button.focus({ preventScroll: true });
    else if (fallback) { fallback.tabIndex = -1; fallback.focus({ preventScroll: true }); }
    remember();
  }
  async function refresh() {
    const ws = workspace(); if (!ws) return;
    const response = await fetch(BASE + "/state/" + ws.dataset.token, { cache: "no-store" });
    if (!response.ok) throw new Error("Не удалось обновить список");
    const template = document.createElement("template"); template.innerHTML = await response.text();
    const next = template.content.firstElementChild; next.hidden = !panel.hidden; ws.replaceWith(next);
    const filter = document.querySelector("[data-review-filter]"); filter.value = state.filter || "all"; filterRows();
    if (panel.hidden) restoreScroll(state.listScroll);
  }
  function advance(message) {
    remember(); announce(message);
    const rows = [...document.querySelectorAll("[data-review-row]")];
    const index = rows.findIndex((row) => row.dataset.reviewRow === String(state.active?.row));
    const following = [...rows.slice(index + 1), ...rows.slice(0, Math.max(0, index))];
    const next = following.filter((row) => !row.hidden && !(state.skipped || []).includes(row.dataset.reviewRow)).map((row) => row.querySelector("[data-manual-person]")).find(Boolean);
    if (next) void open(next.dataset.manualOpen, next.dataset.manualPerson);
    else close();
  }
  document.addEventListener("click", (event) => {
    const target = event.target;
    if (target.closest("a")) remember();
    const opener = target.closest("[data-manual-open]");
    if (opener) { event.preventDefault(); state.skipped = (state.skipped || []).filter((r) => r !== opener.dataset.manualPerson); filterRows(); void open(opener.dataset.manualOpen, opener.dataset.manualPerson || opener.closest('[data-review-row]')?.dataset.reviewRow || null); return; }
    if (target.closest("[data-manual-close]")) { close(); return; }
    if (target.closest("[data-manual-skip]")) { state.skipped ||= []; if (state.active?.row && !state.skipped.includes(String(state.active.row))) state.skipped.push(String(state.active.row)); filterRows(); advance("Кавалер отложен и не войдёт в общий импорт, пока вы не откроете его снова."); return; }
    if (target.closest("[data-manual-next]")) { advance("Решение сохранено. Остались только нерешённые строки."); return; }
    const history = target.closest("[data-review-history]");
    if (history) { void open(history.dataset.reviewHistory, state.active?.row); return; }
    if (target.closest("[data-review-reset-file]")) {
      if (confirm("Закрыть файл и убрать несохранённый выбор? Уже сохранённые данные останутся в базе.")) {
        try { sessionStorage.removeItem(KEY); } catch (_) { /* Optional storage. */ }
        location.href = BASE + "?new=1";
      }
      return;
    }
    const reset = target.closest("[data-review-reset]");
    if (reset) { reset.closest("[data-review-field]").querySelectorAll("input[type=radio]").forEach((r) => { r.checked = false; }); updateChoices(); remember(); return; }
    if (target.closest("[data-manual-undo]")) {
      if (draft?.nodes) { content.replaceChildren(...draft.nodes); state.active = draft.active; draft = null; updateChoices(); remember(); }
      else if (state.active?.row) void open(BASE + "/review/" + state.token + "/" + state.active.row, state.active.row);
      else close();
      return;
    }
    const option = target.closest(".review-option");
    if (option && !target.closest("input,label,details,button,a")) option.querySelector("input[type=radio]")?.click();
  });
  document.addEventListener("change", () => { filterRows(); updateChoices(); remember(); });
  document.addEventListener("submit", async (event) => {
    const form = event.target;
    if (!form.matches("[data-manual-plan],[data-manual-commit],[data-import-plan],[data-manual-history]")) return;
    event.preventDefault(); remember();
    const data = new FormData(form), prior = [...content.childNodes], previous = state.active ? { ...state.active } : null;
    const submit = form.querySelector("button[type=submit]"); if (submit) submit.disabled = true;
    const isPlan = form.matches("[data-manual-plan],[data-import-plan]");
    if (form.matches("[data-import-plan]")) { panel.hidden = false; page.classList.add("bio-detail-open"); workspace().hidden = true; panel.scrollIntoView({ block: "start" }); }
    try {
      let url = form.action, options = { method: "POST", body: data };
      if (form.matches("[data-manual-history]")) { const u = new URL(url); if (data.get("person_id")) u.searchParams.set("person_id", data.get("person_id")); url = u; options = {}; }
      const response = await fragment(url, options);
      if (!response.ok) {
        const error = content.querySelector("[role=alert]");
        if (prior.length && previous && !(form.matches("[data-manual-commit]") && response.status === 409)) { content.replaceChildren(...prior); if (error) content.prepend(error); }
        try { await refresh(); } catch (_) { /* Keep the specific validation explanation. */ }
      } else if (isPlan) {
        draft = { nodes: form.matches("[data-manual-plan]") ? prior : null, active: previous };
        const operation = content.querySelector("[name=plan_token],[name=operation]")?.value;
        state.active = { url: BASE + "/confirm/" + operation, row: previous?.row || null };
      } else if (content.querySelector("[data-manual-result]")) {
        const message = content.querySelector("[data-manual-result]").textContent;
        if (state.active?.row) delete (state.drafts || {})[state.active.row];
        await refresh(); announce(message);
      }
      remember();
    } catch (_) {
      content.replaceChildren(...prior);
      const error = document.createElement("p"); error.setAttribute("role", "alert"); error.textContent = "Связь прервана. Можно повторить это подтверждение: повторная запись исключена."; content.prepend(error);
    } finally { if (submit) submit.disabled = false; }
  });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape" && !panel.hidden) { event.preventDefault(); close(); } });
  window.addEventListener("pagehide", remember);
  window.addEventListener("pageshow", (event) => {
    if (!event.persisted) return;
    try { if (!sessionStorage.getItem(KEY)) { location.replace(BASE + "?new=1"); return; } } catch (_) {}
    void refresh().then(() => { if (state.active) return open(state.active.url, state.active.row, true); });
  });
  const ws = workspace();
  if (new URL(location.href).searchParams.has("new")) { state = {}; try { sessionStorage.removeItem(KEY); } catch (_) {} history.replaceState(null,"",BASE); }
  else if (!ws && location.pathname === BASE && /^[0-9a-f]{64}$/.test(state.token || "")) { location.replace(BASE + "/preview/" + state.token + "#bio-review"); return; }
  else if (!ws && location.pathname.startsWith(BASE + "/preview/")) { state = {}; try { sessionStorage.removeItem(KEY); } catch (_) {} }
  if (ws) {
    const fresh = state.token !== ws.dataset.token;
    if (fresh) state = {};
    state.token = ws.dataset.token;
    history.replaceState(null,"",BASE + "/preview/" + state.token + "#bio-review");
    const filter = document.querySelector("[data-review-filter]"); filter.value = state.filter || "all"; filterRows();
    const active = state.active;
    if (active && allowed(active.url)) void open(active.url, active.row, true);
    else requestAnimationFrame(() => { if (fresh) ws.scrollIntoView({ block: "start" }); else restoreScroll(state.listScroll); });
    remember();
  }
})();
