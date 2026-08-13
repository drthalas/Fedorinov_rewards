(() => {
  "use strict";

  const STORAGE_KEY = "fedorinov:search-session-url";
  const DEFAULT_URL = "/legacy?tab=search";
  let resetNavigation = false;

  function searchUrl(value) {
    try {
      const url = new URL(value, window.location.origin);
      if (url.origin !== window.location.origin || url.pathname !== "/legacy") return null;
      if (url.searchParams.get("tab") !== "search") return null;
      return url;
    } catch (error) {
      return null;
    }
  }

  function hasResultsState(url) {
    return Boolean((url.searchParams.get("q") || "").trim()) ||
      (url.searchParams.get("scope") || "all") !== "all";
  }

  function storedUrl() {
    try {
      const url = searchUrl(window.sessionStorage.getItem(STORAGE_KEY) || "");
      return url && hasResultsState(url) ? `${url.pathname}${url.search}${url.hash}` : "";
    } catch (error) {
      return "";
    }
  }

  function updateNavigation(url = storedUrl()) {
    document.querySelectorAll("[data-search-nav]").forEach((link) => {
      link.href = url || DEFAULT_URL;
    });
  }

  function saveCurrentUrl() {
    if (resetNavigation) return false;
    const url = searchUrl(window.location.href);
    if (!url || !hasResultsState(url)) return false;
    const value = `${url.pathname}${url.search}${url.hash}`;
    try {
      window.sessionStorage.setItem(STORAGE_KEY, value);
      updateNavigation(value);
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
    document.querySelectorAll("[data-search-reset]").forEach((link) => {
      if (link.dataset.searchResetBound === "true") return;
      link.dataset.searchResetBound = "true";
      link.addEventListener("click", clear);
    });
  }

  document.addEventListener("DOMContentLoaded", initialize);
  window.addEventListener("pageshow", initialize);
  window.addEventListener("pagehide", saveCurrentUrl);

  window.FedorinovSearchSessionState = {
    clear,
    saveCurrentUrl,
    storedUrl,
    updateNavigation,
  };
})();
