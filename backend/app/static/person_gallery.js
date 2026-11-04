(() => {
  "use strict";
  const root = document.querySelector("[data-person-gallery]");
  if (!root) return;
  const grid = root.querySelector("[data-gallery-grid]");
  const empty = root.querySelector("[data-gallery-empty]"), error = root.querySelector("[data-gallery-error]");
  const loading = root.querySelector("[data-gallery-loading]");
  const pending = new Set(), failed = new Set(), missing = new Set();
  let unavailable = root.dataset.galleryUnavailable === "true", refreshing = false, refreshAgain = false;
  const hosts = () => [...root.querySelectorAll("[data-gallery-photo]")];
  function status() {
    for (const host of hosts()) {
      host.hidden = missing.has(host) || failed.has(host) || pending.has(host.querySelector("img"));
    }
    error.hidden = !unavailable && !failed.size;
    loading.hidden = !pending.size;
    empty.hidden = hosts().some(h => !h.hidden) || pending.size > 0 || !error.hidden;
  }
  function bind(host) {
    const image = host.querySelector("img");
    pending.add(image);
    image.addEventListener("load", () => { pending.delete(image); failed.delete(host); missing.delete(host); status(); });
    image.addEventListener("error", async () => {
      pending.delete(image); failed.add(host); status();
      try {
        // The gallery opts into strict media responses: a missing file is 404,
        // never the normal /media fallback. 5xx/network/decode errors stay retryable.
        const response = await fetch(image.src, { method: "HEAD", cache: "no-store" });
        if (!image.isConnected) return;
        if (response.status === 404) { missing.add(host); failed.delete(host); }
      } catch (_) { /* Absence is unconfirmed; keep the retry state. */ }
      status();
    });
    if (image.complete) {
      if (image.naturalWidth) pending.delete(image);
      else image.dispatchEvent(new Event("error"));
    }
  }
  hosts().forEach(bind);status();
  async function refresh() {
    if (refreshing) { refreshAgain = true; return; }
    refreshing = true;
    try {
      const response = await fetch(location.pathname + location.search, { cache: "no-store" });
      if (!response.ok) throw new Error();
      const next = new DOMParser().parseFromString(await response.text(), "text/html").querySelector("[data-person-gallery]");
      if (!next) throw new Error();
      unavailable = next.dataset.galleryUnavailable === "true";
      const key = h => JSON.stringify([h.dataset.galleryPath, h.querySelector("img").alt]);
      const current = new Map([...grid.children].map(h => [key(h), h]));
      const keep = new Set();
      for (const candidate of next.querySelector("[data-gallery-grid]").children) {
        const old = current.get(key(candidate));
        if (old && !failed.has(old) && !missing.has(old)) {
          // Preserve loaded valid images and captions; update navigation indexes.
          old.querySelector("a").href = candidate.querySelector("a").href;
          grid.append(old);keep.add(old);
        } else {
          const host = document.importNode(candidate, true);
          grid.append(host);bind(host);keep.add(host);
        }
      }
      for (const host of [...grid.children]) if (!keep.has(host)) {
        pending.delete(host.querySelector("img"));failed.delete(host);missing.delete(host);host.remove();
      }
      // Rebuild a failed/stale slideshow only on this explicit refresh.
      const slide = root.querySelector(".slideshow"), nextSlide = next.querySelector(".slideshow");
      if (slide && (!nextSlide || failed.has(slide) || missing.has(slide) || slide.dataset.galleryPath !== nextSlide.dataset.galleryPath)) {
        pending.delete(slide.querySelector("img"));failed.delete(slide);missing.delete(slide);slide.remove();
        if (nextSlide) { const host = document.importNode(nextSlide, true);grid.before(host);bind(host); }
      }
    } catch (_) { unavailable = true; }
    finally { refreshing = false;status();if (refreshAgain) { refreshAgain = false;void refresh(); } }
  }
  root.querySelector("[data-gallery-retry]").addEventListener("click", refresh);
  window.addEventListener("photos:changed", refresh);
  window.addEventListener("focus", refresh);
  window.addEventListener("pageshow", event => { if (event.persisted) void refresh(); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) void refresh(); });
})();
