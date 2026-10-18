(function () {
  "use strict";

  const MIN_COLUMN_WIDTH = 48;
  const MIN_ROW_HEIGHT = 28;
  const MIN_PHOTO_FRAME_SIZE = 30;
  const MAX_PHOTO_FRAME_SIZE = 120;
  const DEFAULT_ROW_HEIGHT_STORAGE_KEY = "search-results-row-height";

  function applyRowPhotoFrameSize(row, rowHeight) {
    if (!row || !row.querySelector(".search-photo-cell--preview")) {
      return;
    }
    const nextSize = Math.max(MIN_PHOTO_FRAME_SIZE, Math.min(MAX_PHOTO_FRAME_SIZE, Math.round(rowHeight - 10)));
    row.style.setProperty("--search-photo-frame-size", `${nextSize}px`);
  }

  const MAX_COLUMN_WIDTH = 1200;
  const MAX_ROW_HEIGHT = 600;
  const sizes = new WeakMap();

  function storageKey(table) {
    const kind = table.dataset.tableSizeKey;
    return kind ? `fedorinov:table-sizes:v1:${kind}` : "";
  }

  function loadSizes(table) {
    const state = { columns: {}, rowHeight: 0 };
    try {
      const key = storageKey(table);
      const raw = key && window.localStorage.getItem(key);
      if (raw) {
        const saved = JSON.parse(raw);
        if (saved && typeof saved.columns === "object" && saved.columns !== null) {
          for (const [column, width] of Object.entries(saved.columns)) {
            if (typeof width === "number" && Number.isFinite(width) && width >= MIN_COLUMN_WIDTH && width <= MAX_COLUMN_WIDTH) state.columns[column] = width;
          }
        }
        if (Number.isFinite(saved?.rowHeight) && saved.rowHeight >= MIN_ROW_HEIGHT && saved.rowHeight <= MAX_ROW_HEIGHT) state.rowHeight = saved.rowHeight;
      } else if (table.hasAttribute("data-sync-row-height")) {
        // Read the old shared height once; future changes belong to this table kind.
        const old = Number(window.localStorage.getItem(DEFAULT_ROW_HEIGHT_STORAGE_KEY));
        if (Number.isFinite(old) && old >= MIN_ROW_HEIGHT && old <= MAX_ROW_HEIGHT) state.rowHeight = old;
      }
    } catch (error) { /* Storage may be disabled or contain invalid JSON. */ }
    sizes.set(table, state);
    return state;
  }

  function persistSizes(table) {
    const key = storageKey(table);
    if (!key) return;
    try { window.localStorage.setItem(key, JSON.stringify(sizes.get(table))); }
    catch (error) { /* Keep in-memory resizing available when storage is blocked. */ }
  }

  function storedRowHeight(table) {
    return sizes.get(table)?.rowHeight || 0;
  }

  function saveRowHeight(table, height) {
    const state = sizes.get(table);
    if (!state || !table.hasAttribute("data-sync-row-height")) return;
    state.rowHeight = Math.min(MAX_ROW_HEIGHT, Math.max(MIN_ROW_HEIGHT, Math.round(height)));
    persistSizes(table);
  }

  function applyColumnSizes(table) {
    const state = sizes.get(table);
    if (!state || !Object.keys(state.columns).length) return;
    const headers = Array.from(table.querySelectorAll("thead th"));
    let total = 0;
    headers.forEach((header) => {
      const width = state.columns[header.dataset.columnKey] || Math.max(MIN_COLUMN_WIDTH, Math.min(MAX_COLUMN_WIDTH, header.getBoundingClientRect().width));
      header.style.width = `${width}px`;
      header.style.minWidth = `${width}px`;
      total += width;
    });
    table.style.width = `${total}px`;
    table.style.minWidth = "0";
  }

  function initSizeReset(table) {
    if (!storageKey(table)) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary-button search-table-size-reset";
    button.textContent = "Сбросить размеры таблицы";
    button.addEventListener("click", () => {
      // An empty state also prevents the legacy shared height from returning.
      sizes.set(table, { columns: {}, rowHeight: 0 });
      persistSizes(table);
      table.style.removeProperty("width");
      table.style.removeProperty("min-width");
      table.style.removeProperty("--search-results-row-height");
      table.querySelectorAll("th").forEach((header) => { header.style.removeProperty("width"); header.style.removeProperty("min-width"); });
      table.querySelectorAll("tbody tr").forEach((row) => { row.style.removeProperty("height"); row.style.removeProperty("--search-photo-frame-size"); });
    });
    table.parentElement.before(button);
  }

  function applyTableRowHeight(table, rowHeight) {
    const nextHeight = Math.min(MAX_ROW_HEIGHT, Math.max(MIN_ROW_HEIGHT, Math.round(rowHeight)));
    table.style.setProperty("--search-results-row-height", `${nextHeight}px`);
    Array.from(table.querySelectorAll("tbody tr")).forEach((row) => {
      row.style.height = `${nextHeight}px`;
      applyRowPhotoFrameSize(row, nextHeight);
    });
  }

  function initColumnResize(table) {
    Array.from(table.querySelectorAll("th")).forEach((header) => {
      if (header.querySelector("[data-column-resize-handle]")) {
        return;
      }
      const handle = document.createElement("span");
      handle.className = "search-column-resize-handle";
      handle.setAttribute("data-column-resize-handle", "");
      handle.setAttribute("data-resize-hint", "Изменить ширину колонки");
      handle.setAttribute("title", "Изменить ширину колонки");
      handle.setAttribute("aria-hidden", "true");
      header.appendChild(handle);

      handle.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        event.stopPropagation();
        if (storageKey(table)) {
          const state = sizes.get(table);
          table.querySelectorAll("thead th[data-column-key]").forEach((item) => {
            state.columns[item.dataset.columnKey] = Math.max(MIN_COLUMN_WIDTH, Math.min(MAX_COLUMN_WIDTH, item.getBoundingClientRect().width));
          });
          applyColumnSizes(table);
        }
        const startX = event.clientX;
        const startWidth = header.getBoundingClientRect().width;
        handle.setPointerCapture(event.pointerId);
        table.classList.add("is-resizing");

        const onMove = (moveEvent) => {
          const nextWidth = Math.min(storageKey(table) ? MAX_COLUMN_WIDTH : Infinity, Math.max(MIN_COLUMN_WIDTH, startWidth + moveEvent.clientX - startX));
          header.style.width = `${nextWidth}px`;
          header.style.minWidth = `${nextWidth}px`;
          if (storageKey(table) && header.dataset.columnKey) {
            sizes.get(table).columns[header.dataset.columnKey] = nextWidth;
            applyColumnSizes(table);
          }
        };

        const onEnd = () => {
          persistSizes(table);
          table.classList.remove("is-resizing");
          handle.removeEventListener("pointermove", onMove);
          handle.removeEventListener("pointerup", onEnd);
          handle.removeEventListener("pointercancel", onEnd);
        };

        handle.addEventListener("pointermove", onMove);
        handle.addEventListener("pointerup", onEnd);
        handle.addEventListener("pointercancel", onEnd);
      });
    });
  }

  function initRowResize(table) {
    const initialHeight = storedRowHeight(table);
    if (initialHeight) {
      applyTableRowHeight(table, initialHeight);
    }

    Array.from(table.querySelectorAll("tbody tr")).forEach((row) => {
      if (row.querySelector("[data-row-resize-handle]")) {
        return;
      }
      row.setAttribute("data-resizable-row", "");
      const firstCell = row.querySelector("td");
      if (!firstCell) {
        return;
      }
      const handle = document.createElement("span");
      handle.className = "search-row-resize-handle";
      handle.setAttribute("data-row-resize-handle", "");
      handle.setAttribute("data-resize-hint", "Изменить высоту строки");
      handle.setAttribute("title", "Изменить высоту строки");
      handle.setAttribute("aria-hidden", "true");
      firstCell.appendChild(handle);

      handle.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const startY = event.clientY;
        const startHeight = row.getBoundingClientRect().height;
        handle.setPointerCapture(event.pointerId);
        table.classList.add("is-resizing");

        const onMove = (moveEvent) => {
          const nextHeight = Math.max(MIN_ROW_HEIGHT, startHeight + moveEvent.clientY - startY);
          if (table.hasAttribute("data-sync-row-height")) {
            applyTableRowHeight(table, nextHeight);
          } else {
            row.style.height = `${nextHeight}px`;
            applyRowPhotoFrameSize(row, nextHeight);
          }
        };

        const onEnd = () => {
          if (table.hasAttribute("data-sync-row-height")) {
            const currentHeight = row.getBoundingClientRect().height;
            saveRowHeight(table, currentHeight);
            applyTableRowHeight(table, currentHeight);
          }
          table.classList.remove("is-resizing");
          handle.removeEventListener("pointermove", onMove);
          handle.removeEventListener("pointerup", onEnd);
          handle.removeEventListener("pointercancel", onEnd);
        };

        handle.addEventListener("pointermove", onMove);
        handle.addEventListener("pointerup", onEnd);
        handle.addEventListener("pointercancel", onEnd);
      });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-resizable-table]").forEach((table) => {
      loadSizes(table);
      applyColumnSizes(table);
      initSizeReset(table);
      initColumnResize(table);
      initRowResize(table);
    });
  });
})();
