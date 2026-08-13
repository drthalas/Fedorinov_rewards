(() => {
  "use strict";

  const STORAGE_KEY = "fedorinov:search-session-url";
  const DEFAULT_URL = "/legacy?tab=search";
  const SUMMARY_STORAGE_KEY = "fedorinov:summary-session-url";
  const SUMMARY_DEFAULT_URL = "/legacy?tab=summary";
  const REWARDS_STORAGE_KEY = "fedorinov:rewards-session-url";
  const REWARDS_DEFAULT_URL = "/legacy?tab=rewards";
  const TRANSIENT_REWARDS_KEYS = new Set(["created", "error", "media_cleanup", "message", "status"]);
  let resetNavigation = false;
  let summaryResetNavigation = false;

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

  function hasSummaryState(url) {
    return url.searchParams.get("summary_applied") === "1";
  }

  function storedSummaryUrl() {
    try {
      const url = summaryUrl(window.sessionStorage.getItem(SUMMARY_STORAGE_KEY) || "");
      return url && hasSummaryState(url) ? `${url.pathname}${url.search}${url.hash}` : "";
    } catch (error) {
      return "";
    }
  }

  function updateSummaryNavigation(url = storedSummaryUrl()) {
    document.querySelectorAll("[data-summary-nav]").forEach((link) => {
      link.href = url || SUMMARY_DEFAULT_URL;
    });
  }

  function saveCurrentSummaryUrl() {
    if (summaryResetNavigation) return false;
    const url = summaryUrl(window.location.href);
    if (!url || !hasSummaryState(url)) return false;
    const value = `${url.pathname}${url.search}${url.hash}`;
    try {
      window.sessionStorage.setItem(SUMMARY_STORAGE_KEY, value);
      updateSummaryNavigation(value);
      return true;
    } catch (error) {
      return false;
    }
  }

  function clearSummary() {
    summaryResetNavigation = true;
    try {
      window.sessionStorage.removeItem(SUMMARY_STORAGE_KEY);
    } catch (error) {
      // Session storage may be disabled; reset navigation must still work.
    }
    updateSummaryNavigation("");
  }

  function rewardsUrl(value) {
    try {
      const url = new URL(value, window.location.origin);
      if (url.origin !== window.location.origin || url.pathname !== "/legacy") return null;
      if (url.searchParams.get("tab") !== "rewards") return null;
      return url;
    } catch (error) {
      return null;
    }
  }

  function selectedRewardsUrl(value) {
    const url = rewardsUrl(value);
    if (!url || !/^\d+$/.test(url.searchParams.get("person_id") || "")) return null;
    TRANSIENT_REWARDS_KEYS.forEach((key) => url.searchParams.delete(key));
    return url;
  }

  function storedRewardsUrl() {
    try {
      const url = selectedRewardsUrl(window.sessionStorage.getItem(REWARDS_STORAGE_KEY) || "");
      return url ? `${url.pathname}${url.search}${url.hash}` : "";
    } catch (error) {
      return "";
    }
  }

  function updateRewardsNavigation(url = storedRewardsUrl()) {
    document.querySelectorAll("[data-rewards-nav]").forEach((link) => {
      link.href = url || REWARDS_DEFAULT_URL;
    });
  }

  function syncCurrentRewardsUrl() {
    const current = rewardsUrl(window.location.href);
    if (!current) {
      updateRewardsNavigation();
      return false;
    }
    const selected = selectedRewardsUrl(current.href);
    try {
      if (!selected) {
        window.sessionStorage.removeItem(REWARDS_STORAGE_KEY);
        updateRewardsNavigation("");
        return false;
      }
      const value = `${selected.pathname}${selected.search}${selected.hash}`;
      window.sessionStorage.setItem(REWARDS_STORAGE_KEY, value);
      updateRewardsNavigation(value);
      return true;
    } catch (error) {
      return false;
    }
  }

  function initialize() {
    resetNavigation = false;
    summaryResetNavigation = false;
    saveCurrentUrl();
    updateNavigation();
    saveCurrentSummaryUrl();
    updateSummaryNavigation();
    syncCurrentRewardsUrl();
    document.querySelectorAll("[data-search-reset]").forEach((link) => {
      if (link.dataset.searchResetBound === "true") return;
      link.dataset.searchResetBound = "true";
      link.addEventListener("click", clear);
    });
    document.querySelectorAll("[data-summary-reset]").forEach((link) => {
      if (link.dataset.summaryResetBound === "true") return;
      link.dataset.summaryResetBound = "true";
      link.addEventListener("click", clearSummary);
    });
  }

  document.addEventListener("DOMContentLoaded", initialize);
  window.addEventListener("pageshow", initialize);
  window.addEventListener("pagehide", () => {
    saveCurrentUrl();
    saveCurrentSummaryUrl();
    syncCurrentRewardsUrl();
  });
  document.addEventListener("legacy:url-updated", syncCurrentRewardsUrl);

  window.FedorinovSearchSessionState = {
    clear,
    saveCurrentUrl,
    storedUrl,
    updateNavigation,
  };
  window.FedorinovTabSessionState = {
    clearSummary,
    saveCurrentSummaryUrl,
    storedRewardsUrl,
    storedSummaryUrl,
    syncCurrentRewardsUrl,
  };
})();
