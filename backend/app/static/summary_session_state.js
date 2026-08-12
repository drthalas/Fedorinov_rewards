(() => {
  "use strict";

  const STORAGE_KEY = "fedorinov:summary-session-url";
  const DEFAULT_URL = "/legacy?tab=summary";
  let resetNavigation = false;

  function summaryUrl(value) {
    try {
      const url = new URL(value, window.location.origin);
      if (url.origin !== window.location.origin || url.pathname !== "/legacy") return null;
      if (url.searchParams.get("tab") !== "summary") return null;
      return url;
    } catch (error) {
      return null;
    }
  }

  function storedUrl() {
    try {
      const url = summaryUrl(window.sessionStorage.getItem(STORAGE_KEY) || "");
      return url && url.searchParams.get("summary_applied") === "1"
        ? `${url.pathname}${url.search}${url.hash}`
        : "";
    } catch (error) {
      return "";
    }
  }

  function updateNavigation(url = storedUrl()) {
    document.querySelectorAll("[data-summary-nav]").forEach((link) => {
      link.href = url || DEFAULT_URL;
    });
  }

  function saveCurrentUrl() {
    if (resetNavigation) return false;
    const url = summaryUrl(window.location.href);
    if (!url || url.searchParams.get("summary_applied") !== "1") return false;
    try {
      window.sessionStorage.setItem(STORAGE_KEY, `${url.pathname}${url.search}${url.hash}`);
      updateNavigation(`${url.pathname}${url.search}${url.hash}`);
      return true;
    } catch (error) {
      return false;
    }
  }

  function clear() {
    resetNavigation = true;
    try {
      window.sessionStorage.removeItem(STORAGE_KEY);
    } catch (error) {
      // Session storage may be disabled; reset navigation must still work.
    }
    updateNavigation("");
  }

  function initialize() {
    resetNavigation = false;
    saveCurrentUrl();
    updateNavigation();
    document.querySelectorAll("[data-summary-reset]").forEach((link) => {
      if (link.dataset.summaryResetBound === "true") return;
      link.dataset.summaryResetBound = "true";
      link.addEventListener("click", clear);
    });
  }

  document.addEventListener("DOMContentLoaded", initialize);
  window.addEventListener("pageshow", initialize);
  window.addEventListener("pagehide", saveCurrentUrl);

  window.FedorinovSummarySessionState = {
    clear,
    saveCurrentUrl,
    storedUrl,
    updateNavigation,
  };
})();
