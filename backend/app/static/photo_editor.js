(() => {
  "use strict";
  const dialog = document.querySelector("[data-photo-editor]");
  if (!dialog) return;
  const find = (name) => dialog.querySelector(`[data-photo-${name}]`);
  const canvas = find("crop"), preview = find("preview"), slider = find("brightness");
  const error = find("editor-error"), save = find("editor-save");
  let source, trigger, slot, crop, start, expected, pendingFile, objectUrl = "", busy = false;
  const fail = (message) => { error.textContent = message; error.hidden = !message; };
  function setBusy(value) {
    busy = value;
    dialog.querySelectorAll("button, input").forEach((control) => { control.disabled = value; });
    save.textContent = value ? "Сохраняем…" : "Сохранить";
  }
  function fit(target, width, height) {
    const ratio = Math.min(1, 1200 / width, 900 / height);
    target.width = Math.max(1, Math.round(width * ratio));
    target.height = Math.max(1, Math.round(height * ratio));
  }
  function draw() {
    const [x, y, width, height] = crop;
    find("brightness-value").value = `${slider.value}%`;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(source, 0, 0, canvas.width, canvas.height);
    const sx = canvas.width / source.naturalWidth, sy = canvas.height / source.naturalHeight;
    ctx.fillStyle = "rgba(0,0,0,.5)";
    ctx.beginPath(); ctx.rect(0, 0, canvas.width, canvas.height);
    ctx.rect(x * sx, y * sy, width * sx, height * sy); ctx.fill("evenodd");
    ctx.strokeStyle = "#fff"; ctx.lineWidth = 2;
    ctx.strokeRect(x * sx, y * sy, width * sx, height * sy);
    fit(preview, width, height);
    const out = preview.getContext("2d");
    out.clearRect(0, 0, preview.width, preview.height);
    out.filter = `brightness(${Number(slider.value) / 100})`;
    out.drawImage(source, x, y, width, height, 0, 0, preview.width, preview.height);
  }
  function reset() { crop = [0, 0, source.naturalWidth, source.naturalHeight]; slider.value = 100; fail(""); draw(); }
  function close() {
    if (busy) return;
    dialog.close(); trigger?.focus();
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = ""; source = null; start = null;
  }
  function syncButtons() {
    document.querySelectorAll("[data-photo-editor-slot]").forEach((host) => {
      const image = host.querySelector("[data-photo-editor-image]");
      const button = host.querySelector("[data-photo-edit]");
      const pending = host.dataset.photoEditKind === "guide" && host.querySelector('input[type="file"]')?.files.length;
      const missingStored = host.dataset.photoEditKind === "guide" && !pending && host.dataset.photoEditStored !== "true";
      const hidden = !image || image.hidden || !image.getAttribute("src") || missingStored;
      if (button && button.hidden !== hidden) button.hidden = hidden;
    });
  }
  let syncFrame = 0;
  new MutationObserver(() => {
    if (!syncFrame) syncFrame = requestAnimationFrame(() => { syncFrame = 0; syncButtons(); });
  }).observe(document.querySelector("main") || document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ["src", "hidden"] });
  syncButtons();
  document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-photo-edit]");
    if (!button || busy) return;
    trigger = button; slot = button.closest("[data-photo-editor-slot]");
    if (!slot) return;
    find("editor-label").textContent = button.dataset.photoLabel;
    fail(""); source = null; canvas.width = preview.width = 1;
    dialog.showModal(); setBusy(true);
    try {
      const image = new Image();
      const currentImage = slot.querySelector("[data-photo-editor-image]");
      pendingFile = slot.dataset.photoEditKind === "guide" && slot.querySelector('input[type="file"]')?.files[0];
      expected = slot.dataset.photoEditPath || "";
      if (slot.dataset.photoEditKind === "draft") {
        const response = await fetch(currentImage.src, { cache: "no-store" });
        if (!response.ok) throw new Error("Фото черновика недоступно.");
        const blob = await response.blob();
        const digest = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
        expected = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
        objectUrl = URL.createObjectURL(blob); image.src = objectUrl;
      } else image.src = currentImage.src;
      await image.decode();
      if (image.naturalWidth * image.naturalHeight > 40000000) throw new Error("Изображение больше 40 миллионов пикселей.");
      source = image; fit(canvas, source.naturalWidth, source.naturalHeight); reset();
    } catch (failure) { fail(failure.message || "Не удалось открыть фото."); }
    finally { setBusy(false); save.disabled = !source; }
  });
  function point(event) {
    const rect = canvas.getBoundingClientRect();
    return [Math.max(0, Math.min(source.naturalWidth, Math.round((event.clientX - rect.left) / rect.width * source.naturalWidth))),
      Math.max(0, Math.min(source.naturalHeight, Math.round((event.clientY - rect.top) / rect.height * source.naturalHeight)))];
  }
  canvas.addEventListener("pointerdown", (event) => {
    if (!source || busy) return;
    event.preventDefault(); start = point(event); canvas.setPointerCapture(event.pointerId); canvas.focus({ preventScroll: true });
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!start || !source || busy) return;
    const end = point(event);
    const x = Math.min(start[0], end[0], source.naturalWidth - 1), y = Math.min(start[1], end[1], source.naturalHeight - 1);
    crop = [x, y, Math.max(1, Math.abs(end[0] - start[0])), Math.max(1, Math.abs(end[1] - start[1]))];
    draw();
  });
  ["pointerup", "pointercancel"].forEach((type) => canvas.addEventListener(type, () => { start = null; }));
  canvas.addEventListener("keydown", (event) => {
    if (!source || busy || !event.key.startsWith("Arrow")) return;
    event.preventDefault();
    const axis = /Left|Right/.test(event.key) ? 0 : 1, delta = /Left|Up/.test(event.key) ? -1 : 1;
    const limit = axis === 0 ? source.naturalWidth : source.naturalHeight;
    if (event.shiftKey) crop[axis + 2] = Math.max(1, Math.min(limit - crop[axis], crop[axis + 2] + delta));
    else crop[axis] = Math.max(0, Math.min(limit - crop[axis + 2], crop[axis] + delta));
    draw();
  });
  slider.addEventListener("input", () => { if (source) draw(); });
  find("editor-reset").addEventListener("click", () => { if (source) reset(); });
  find("editor-cancel").addEventListener("click", close);
  dialog.addEventListener("keydown", (event) => {
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); }
  });
  dialog.addEventListener("cancel", (event) => { event.preventDefault(); close(); });
  async function stageFile() {
    const output = document.createElement("canvas");
    output.width = crop[2]; output.height = crop[3];
    const context = output.getContext("2d");
    context.filter = `brightness(${Number(slider.value) / 100})`;
    context.drawImage(source, ...crop, 0, 0, output.width, output.height);
    const blob = await new Promise((resolve) => output.toBlob(resolve, "image/png"));
    if (!blob || blob.size > 5 * 1024 * 1024) throw new Error("Результат больше 5 MB. Выберите меньшую область.");
    const file = new File([blob], "edited.png", { type: "image/png" });
    const transfer = new DataTransfer(); transfer.items.add(file);
    slot.querySelector('input[type="file"]').files = transfer.files;
    slot.dispatchEvent(new CustomEvent("photo-editor:staged", { bubbles: true, detail: { file } }));
  }
  save.addEventListener("click", async () => {
    if (!source || busy) return;
    setBusy(true); fail("");
    const field = trigger.dataset.photoField;
    try {
      if (pendingFile) await stageFile();
      else {
        const response = await fetch(slot.dataset.photoEditUrl, { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ photo_field: field, expected_path: expected, crop, brightness: Number(slider.value) / 100 }) });
        const payload = await response.json();
        if (!response.ok || !payload.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : "Не удалось сохранить фото.");
        slot.querySelector("[data-photo-editor-image]").src = payload.url;
        if (payload.path) {
          slot.dataset.photoEditPath = payload.path;
          slot.dataset.photoEditStored = "true";
          const link = slot.querySelector("a.photo-link");
          if (link) { const url = new URL(link.href); url.searchParams.set("path", payload.path); link.href = url.href; link.dataset.lightboxSrc = payload.url; }
          document.querySelectorAll(`.edit-form input[type="hidden"][name="${field}"]`).forEach((input) => { input.value = payload.path; });
        }
        slot.dispatchEvent(new CustomEvent("photo-editor:saved", { bubbles: true, detail: payload }));
        if (payload.cleanup_warning) {
          const warning = slot.querySelector("[data-photo-source-error]");
          if (warning) { warning.textContent = "Фото сохранено. Старый файл не удалось удалить."; warning.hidden = false; }
        }
      }
      setBusy(false); close();
    } catch (failure) { fail(failure.message || "Не удалось сохранить фото. Повторите попытку."); }
    finally { setBusy(false); }
  });
})();
