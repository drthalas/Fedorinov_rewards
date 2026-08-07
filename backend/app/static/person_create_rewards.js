(function () {
  "use strict";

  function init(root) {
    const section = (root || document).querySelector("[data-pending-rewards]");
    if (!section || section.dataset.pendingRewardsReady === "true") return;
    section.dataset.pendingRewardsReady = "true";

    const list = section.querySelector("[data-pending-reward-list]");
    const template = section.querySelector("[data-pending-reward-template]");
    const addButton = section.querySelector("[data-add-pending-reward]");
    let nextIndex = list.querySelectorAll("[data-pending-reward]").length;

    function refreshTitles() {
      list.querySelectorAll("[data-pending-reward]").forEach((row, index) => {
        const title = row.querySelector("[data-pending-reward-title]");
        if (title) title.textContent = `Награда ${index + 1}`;
      });
    }

    function bindRemove(row) {
      const remove = row.querySelector("[data-remove-pending-reward]");
      if (!remove || remove.dataset.pendingRewardRemoveReady === "true") return;
      remove.dataset.pendingRewardRemoveReady = "true";
      remove.addEventListener("click", () => {
        row.remove();
        refreshTitles();
        addButton.focus({ preventScroll: true });
      });
    }

    list.querySelectorAll("[data-pending-reward]").forEach(bindRemove);
    refreshTitles();

    addButton.addEventListener("click", () => {
      const holder = document.createElement("div");
      holder.innerHTML = template.innerHTML.replaceAll("__INDEX__", String(nextIndex++));
      const row = holder.firstElementChild;
      if (!row) return;
      list.appendChild(row);
      bindRemove(row);
      refreshTitles();
      document.dispatchEvent(new CustomEvent("legacy:content-updated", { detail: { root: row } }));
      const firstControl = row.querySelector("button, input, select");
      if (firstControl) firstControl.focus({ preventScroll: true });
      row.scrollIntoView({ block: "nearest" });
    });
  }

  document.addEventListener("DOMContentLoaded", () => init(document));
})();
