(function () {
  "use strict";

  let instanceCounter = 0;

  function initStyledSelect(select) {
    if (!(select instanceof HTMLSelectElement) || select.dataset.styledSelectReady === "true") {
      return;
    }
    select.dataset.styledSelectReady = "true";
    select.classList.add("styled-select-native");
    select.tabIndex = -1;
    select.setAttribute("aria-hidden", "true");

    const wrapper = document.createElement("div");
    wrapper.className = "styled-select";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "styled-select-button";
    button.setAttribute("role", "combobox");
    button.setAttribute("aria-haspopup", "listbox");
    button.setAttribute("aria-expanded", "false");
    const value = document.createElement("span");
    value.className = "styled-select-value";
    const chevron = document.createElement("span");
    chevron.className = "styled-select-chevron";
    chevron.setAttribute("aria-hidden", "true");
    button.append(value, chevron);

    const listbox = document.createElement("div");
    const listboxId = `styled-select-${++instanceCounter}`;
    listbox.id = listboxId;
    listbox.className = "styled-select-listbox";
    listbox.setAttribute("role", "listbox");
    listbox.hidden = true;
    button.setAttribute("aria-controls", listboxId);
    wrapper.append(button, listbox);
    select.insertAdjacentElement("afterend", wrapper);

    let activeIndex = -1;

    const optionButtons = () => Array.from(listbox.querySelectorAll("[role='option']"));
    const selectedIndex = () => Math.max(0, select.selectedIndex);

    function close(options) {
      const settings = options || {};
      wrapper.classList.remove("is-open");
      listbox.hidden = true;
      button.setAttribute("aria-expanded", "false");
      button.removeAttribute("aria-activedescendant");
      if (settings.focusButton) {
        button.focus({ preventScroll: true });
      }
    }

    function setActive(index, scroll) {
      const options = optionButtons();
      if (!options.length) {
        activeIndex = -1;
        return;
      }
      activeIndex = Math.max(0, Math.min(index, options.length - 1));
      options.forEach((option, optionIndex) => option.classList.toggle("is-active", optionIndex === activeIndex));
      const active = options[activeIndex];
      button.setAttribute("aria-activedescendant", active.id);
      if (scroll) {
        active.scrollIntoView({ block: "nearest" });
      }
    }

    function choose(index) {
      const option = select.options[index];
      if (!option || option.disabled) {
        return;
      }
      select.selectedIndex = index;
      sync();
      select.dispatchEvent(new Event("input", { bubbles: true }));
      select.dispatchEvent(new Event("change", { bubbles: true }));
      close({ focusButton: true });
    }

    function rebuild() {
      const fragment = document.createDocumentFragment();
      Array.from(select.options).forEach((option, index) => {
        const item = document.createElement("button");
        item.type = "button";
        item.id = `${listboxId}-option-${index}`;
        item.className = "styled-select-option";
        item.setAttribute("role", "option");
        item.setAttribute("aria-selected", option.selected ? "true" : "false");
        item.dataset.optionIndex = String(index);
        item.textContent = option.textContent || "—";
        item.disabled = option.disabled;
        item.addEventListener("click", () => choose(index));
        fragment.appendChild(item);
      });
      listbox.replaceChildren(fragment);
      sync();
    }

    function sync() {
      const option = select.options[select.selectedIndex];
      value.textContent = option ? option.textContent : "—";
      button.disabled = select.disabled;
      optionButtons().forEach((item, index) => {
        item.setAttribute("aria-selected", index === select.selectedIndex ? "true" : "false");
      });
      activeIndex = selectedIndex();
    }

    function open() {
      if (button.disabled) {
        return;
      }
      document.dispatchEvent(new CustomEvent("styled-select:open", { detail: { wrapper } }));
      wrapper.classList.add("is-open");
      listbox.hidden = false;
      button.setAttribute("aria-expanded", "true");
      setActive(selectedIndex(), true);
    }

    button.addEventListener("click", () => {
      if (wrapper.classList.contains("is-open")) {
        close();
      } else {
        open();
      }
    });

    button.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        if (!wrapper.classList.contains("is-open")) {
          open();
        } else {
          setActive(activeIndex + (event.key === "ArrowDown" ? 1 : -1), true);
        }
      } else if (event.key === "Home" || event.key === "End") {
        if (!wrapper.classList.contains("is-open")) {
          return;
        }
        event.preventDefault();
        setActive(event.key === "Home" ? 0 : optionButtons().length - 1, true);
      } else if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        if (!wrapper.classList.contains("is-open")) {
          open();
        } else {
          choose(activeIndex);
        }
      } else if (event.key === "Escape") {
        if (wrapper.classList.contains("is-open")) {
          event.preventDefault();
          close();
        }
      } else if (event.key === "Tab") {
        close();
      }
    });

    select.addEventListener("change", sync);
    document.addEventListener("styled-select:open", (event) => {
      if (!event.detail || event.detail.wrapper !== wrapper) {
        close();
      }
    });
    document.addEventListener("pointerdown", (event) => {
      if (!wrapper.contains(event.target)) {
        close();
      }
    });

    const observer = new MutationObserver(rebuild);
    observer.observe(select, { childList: true, subtree: true, attributes: true, attributeFilter: ["selected", "disabled"] });
    rebuild();
  }

  function initAll(root) {
    const scope = root || document;
    scope.querySelectorAll("select[data-styled-select]").forEach(initStyledSelect);
  }

  document.addEventListener("DOMContentLoaded", () => initAll(document));
  document.addEventListener("legacy:content-updated", (event) => initAll(event.detail && event.detail.root ? event.detail.root : document));
})();
