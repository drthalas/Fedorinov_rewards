(() => {
  "use strict";

  const LEGACY_STATE_PREFIX = "fedorinov:legacy-list-state:";
  const OPEN_FOLDER_TIMEOUT_MS = 15000;
  const TRANSIENT_QUERY_KEYS = new Set([
    "created",
    "error",
    "mark_id",
    "media_cleanup",
    "message",
    "person_id",
    "status",
  ]);
  const activeOpenFolderForms = new WeakMap();

  function stableLegacyStateKey(urlValue) {
    let url;
    try {
      url = new URL(urlValue || window.location.href, window.location.origin);
    } catch (error) {
      return "";
    }
    if (url.origin !== window.location.origin || url.pathname !== "/legacy") return "";
    Array.from(url.searchParams.keys()).forEach((key) => {
      if (TRANSIENT_QUERY_KEYS.has(key)) url.searchParams.delete(key);
    });
    url.searchParams.sort();
    return `${LEGACY_STATE_PREFIX}${url.pathname}?${url.searchParams.toString()}`;
  }

  function saveLegacyState() {
    const key = stableLegacyStateKey(window.location.href);
    if (!key) return false;
    const personList = document.querySelector("[data-person-list]");
    const sidebarList = document.querySelector(".legacy-sidebar .legacy-list");
    if (!personList && !sidebarList) return false;
    const quickSearch = document.querySelector("[data-person-quick-search]");
    const state = {
      personListScrollTop: personList ? personList.scrollTop : null,
      sidebarListScrollTop: sidebarList ? sidebarList.scrollTop : null,
      quickSearch: quickSearch ? quickSearch.value : "",
      selectedPersonId: new URL(window.location.href).searchParams.get("person_id"),
    };
    try {
      window.sessionStorage.setItem(key, JSON.stringify(state));
      return true;
    } catch (error) {
      return false;
    }
  }

  function storedLegacyState(urlValue) {
    const key = stableLegacyStateKey(urlValue);
    if (!key) return null;
    try {
      const state = JSON.parse(window.sessionStorage.getItem(key) || "null");
      return state && typeof state === "object" ? state : null;
    } catch (error) {
      return null;
    }
  }

  function restoreLegacyState(root = document) {
    const state = storedLegacyState(window.location.href);
    if (!state) return false;
    const personList = root.querySelector("[data-person-list]");
    const sidebarList = root.querySelector(".legacy-sidebar .legacy-list");
    const quickSearch = root.querySelector("[data-person-quick-search]");
    if (personList && Number.isFinite(Number(state.personListScrollTop))) {
      personList.scrollTop = Math.max(0, Number(state.personListScrollTop));
      personList.dataset.scrollRestored = "true";
    }
    if (sidebarList && sidebarList !== personList && Number.isFinite(Number(state.sidebarListScrollTop))) {
      sidebarList.scrollTop = Math.max(0, Number(state.sidebarListScrollTop));
      sidebarList.dataset.scrollRestored = "true";
    }
    if (quickSearch && typeof state.quickSearch === "string") {
      quickSearch.value = state.quickSearch;
    }
    return true;
  }

  function restoreLegacySelectionTarget(link) {
    if (!link || !link.href) return;
    let current;
    let target;
    try {
      current = new URL(window.location.href);
      target = new URL(link.href, current);
    } catch (error) {
      return;
    }
    const returningToRewards = target.origin === current.origin
      && target.pathname === "/legacy"
      && target.searchParams.get("tab") === "rewards"
      && !target.searchParams.has("person_id");
    const alreadyInRewards = current.pathname === "/legacy" && current.searchParams.get("tab") === "rewards";
    if (!returningToRewards || alreadyInRewards) return;
    const state = storedLegacyState(target.href);
    const personId = String((state && state.selectedPersonId) || "");
    if (!/^\d+$/.test(personId)) return;
    target.searchParams.set("person_id", personId);
    link.href = `${target.pathname}${target.search}${target.hash}`;
  }

  function beginNavigation(message = "Открываем…") {
    saveLegacyState();
    document.documentElement.dataset.navigationPending = "true";
    const feedback = window.FedorinovWriteFeedback;
    if (feedback && typeof feedback.showStatus === "function") {
      feedback.showStatus(message, "pending");
    }
  }

  function resetNavigation() {
    delete document.documentElement.dataset.navigationPending;
  }

  function eligibleInternalLink(event, link) {
    if (!link || event.defaultPrevented || event.button !== 0) return false;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return false;
    if (link.hasAttribute("download") || link.dataset.noTransition !== undefined) return false;
    if (link.target && link.target.toLowerCase() !== "_self") return false;
    if (link.closest(".photo-link, [data-lightbox-src], [data-save-as-form], [data-update-form]")) return false;
    let target;
    try {
      target = new URL(link.href, window.location.href);
    } catch (error) {
      return false;
    }
    if (target.origin !== window.location.origin || !/^https?:$/.test(target.protocol)) return false;
    const current = new URL(window.location.href);
    return target.pathname !== current.pathname || target.search !== current.search;
  }

  async function submitOpenFolder(form, submitter) {
    const feedback = window.FedorinovWriteFeedback;
    if (!feedback || typeof feedback.begin !== "function" || typeof feedback.finish !== "function") return;
    if (!feedback.begin(form, submitter, form.dataset.writePendingLabel || "Открываем каталог…")) return;

    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), OPEN_FOLDER_TIMEOUT_MS);
    activeOpenFolderForms.set(form, controller);
    try {
      const response = await window.fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        credentials: "same-origin",
        headers: {
          "Accept": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        signal: controller.signal,
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.ok !== true) {
        throw new Error(String(payload.message || payload.detail || "Не удалось открыть каталог."));
      }
      feedback.finish(form, { state: "success", message: String(payload.message || "Каталог кавалера открыт.") });
    } catch (error) {
      const message = error && error.name === "AbortError"
        ? "Каталог открывается слишком долго. Повторите попытку."
        : String((error && error.message) || "Не удалось открыть каталог.");
      feedback.finish(form, { state: "error", message });
    } finally {
      window.clearTimeout(timeoutId);
      if (activeOpenFolderForms.get(form) === controller) activeOpenFolderForms.delete(form);
    }
  }

  document.addEventListener("click", (event) => {
    const link = event.target instanceof Element ? event.target.closest("a[href]") : null;
    restoreLegacySelectionTarget(link);
    if (eligibleInternalLink(event, link)) beginNavigation(link.dataset.transitionLabel || "Открываем…");
  });

  document.addEventListener("submit", (event) => {
    const form = event.target instanceof HTMLFormElement ? event.target : null;
    if (!form) return;
    if (form.matches("[data-open-folder]")) {
      if (!window.fetch || !window.FormData || !window.AbortController || !window.FedorinovWriteFeedback) return;
      event.preventDefault();
      if (activeOpenFolderForms.has(form)) {
        event.stopImmediatePropagation();
        return;
      }
      void submitOpenFolder(form, event.submitter || null);
      return;
    }
    if (event.defaultPrevented || form.matches("[data-save-as-form], [data-update-form]")) return;
    saveLegacyState();
    if ((form.method || "get").toLowerCase() === "get") {
      beginNavigation(form.dataset.transitionLabel || "Загружаем…");
    }
  });

  window.addEventListener("pagehide", saveLegacyState);
  window.addEventListener("pageshow", () => {
    resetNavigation();
    restoreLegacyState(document);
  });
  document.addEventListener("DOMContentLoaded", () => restoreLegacyState(document));

  window.FedorinovTransitionLifecycle = Object.freeze({
    beginNavigation,
    restoreLegacyState,
    saveLegacyState,
  });
})();
