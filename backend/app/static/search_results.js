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

  function rowHeightStorageKey(table) {
    return table.getAttribute("data-row-height-storage-key") || DEFAULT_ROW_HEIGHT_STORAGE_KEY;
  }

  function storedRowHeight(table) {
    if (!table.hasAttribute("data-sync-row-height")) {
      return 0;
    }
    try {
      const value = Number.parseFloat(window.localStorage.getItem(rowHeightStorageKey(table)) || "");
      return Number.isFinite(value) && value >= MIN_ROW_HEIGHT ? value : 0;
    } catch (error) {
      return 0;
    }
  }

  function saveRowHeight(table, rowHeight) {
    if (!table.hasAttribute("data-sync-row-height")) {
      return;
    }
    try {
      window.localStorage.setItem(rowHeightStorageKey(table), String(Math.round(rowHeight)));
    } catch (error) {
      // localStorage can be unavailable in restricted browser modes; visual resize still works.
    }
  }

  function applyTableRowHeight(table, rowHeight) {
    const nextHeight = Math.max(MIN_ROW_HEIGHT, Math.round(rowHeight));
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
        const startX = event.clientX;
        const startWidth = header.getBoundingClientRect().width;
        handle.setPointerCapture(event.pointerId);
        table.classList.add("is-resizing");

        const onMove = (moveEvent) => {
          const nextWidth = Math.max(MIN_COLUMN_WIDTH, startWidth + moveEvent.clientX - startX);
          header.style.width = `${nextWidth}px`;
          header.style.minWidth = `${nextWidth}px`;
        };

        const onEnd = () => {
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
      initColumnResize(table);
      initRowResize(table);
    });
  });
})();
