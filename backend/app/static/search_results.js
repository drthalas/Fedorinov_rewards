(function () {
  "use strict";

  const MIN_COLUMN_WIDTH = 48;
  const MIN_ROW_HEIGHT = 28;

  function initColumnResize(table) {
    Array.from(table.querySelectorAll("th")).forEach((header) => {
      if (header.querySelector("[data-column-resize-handle]")) {
        return;
      }
      const handle = document.createElement("span");
      handle.className = "search-column-resize-handle";
      handle.setAttribute("data-column-resize-handle", "");
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
          row.style.height = `${nextHeight}px`;
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

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-resizable-table]").forEach((table) => {
      initColumnResize(table);
      initRowResize(table);
    });
  });
})();
