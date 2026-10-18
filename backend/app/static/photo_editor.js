(() => {
  "use strict";
  const dialog = document.querySelector("[data-photo-editor]");
  if (!dialog) return;
  const find = (name) => dialog.querySelector(`[data-photo-${name}]`);
  const canvas = find("crop"), preview = find("preview"), slider = find("brightness");
  const error = find("editor-error"), save = find("editor-save");
  const inputs = [...dialog.querySelectorAll("[data-crop-value]")];
  let source, trigger, crop, start, busy = false, opening = 0;
  const fail = (message) => { error.textContent = message; error.hidden = !message; };
  function setBusy(value) {
    busy = value;
    dialog.querySelectorAll("button, input").forEach((control) => { control.disabled = value; });
    save.textContent = value ? "Сохраняем…" : "Сохранить";
  }
  function fit(target, width, height) {
    const ratio = Math.min(1, 800 / width, 600 / height);
    target.width = Math.max(1, Math.round(width * ratio));
    target.height = Math.max(1, Math.round(height * ratio));
  }
  function draw() {
    const [x, y, width, height] = crop;
    inputs.forEach((input, index) => { input.value = crop[index]; });
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
  function close() { if (!busy) { opening += 1; dialog.close(); trigger?.focus(); } }
  document.querySelectorAll("[data-photo-edit]").forEach((button) => {
    button.addEventListener("click", async () => {
      trigger = button; const attempt = ++opening;
      find("editor-label").textContent = button.dataset.photoLabel;
      fail(""); dialog.showModal(); setBusy(true);
      try {
        const image = new Image(); image.src = button.closest(".photo-manage-card").querySelector("img.photo").src;
        await image.decode();
        if (attempt !== opening) return;
        if (image.naturalWidth * image.naturalHeight > 40000000) throw new Error("Изображение больше 40 миллионов пикселей.");
        source = image; fit(canvas, source.naturalWidth, source.naturalHeight); reset();
      } catch (failure) { fail(failure.message || "Не удалось открыть фото."); source = null; }
      finally { setBusy(false); save.disabled = !source; }
    });
  });
  function point(event) {
    const rect = canvas.getBoundingClientRect();
    return [Math.max(0, Math.min(source.naturalWidth - 1, Math.round((event.clientX - rect.left) / rect.width * source.naturalWidth))),
      Math.max(0, Math.min(source.naturalHeight - 1, Math.round((event.clientY - rect.top) / rect.height * source.naturalHeight)))];
  }
  canvas.addEventListener("pointerdown", (event) => {
    if (!source || busy) return; event.preventDefault(); start = point(event); canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!start || !source || busy) return;
    const end = point(event);
    crop = [Math.min(start[0], end[0]), Math.min(start[1], end[1]), Math.max(1, Math.abs(end[0] - start[0])), Math.max(1, Math.abs(end[1] - start[1]))];
    draw();
  });
  ["pointerup", "pointercancel"].forEach((type) => canvas.addEventListener(type, () => { start = null; }));
  inputs.forEach((input) => input.addEventListener("change", () => {
    if (!source) return;
    const values = inputs.map((item) => Number(item.value));
    if (values.every(Number.isInteger) && values[0] >= 0 && values[1] >= 0 && values[2] > 0 && values[3] > 0 &&
        values[0] + values[2] <= source.naturalWidth && values[1] + values[3] <= source.naturalHeight) {
      crop = values; fail(""); draw();
    } else { fail("Область обрезки выходит за границы изображения."); draw(); }
  }));
  slider.addEventListener("input", () => { if (source) draw(); });
  find("editor-reset").addEventListener("click", () => { if (source) reset(); });
  find("editor-cancel").addEventListener("click", close);
  dialog.addEventListener("keydown", (event) => {
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); }
  });
  dialog.addEventListener("cancel", (event) => { event.preventDefault(); close(); });
  save.addEventListener("click", async () => {
    if (!source || busy) return;
    setBusy(true); fail("");
    const field = trigger.dataset.photoField;
    try {
      const response = await fetch(`/rewards/${trigger.dataset.rewardId}/photos/edit`, { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ photo_field: field,
          expected_path: trigger.dataset.photoPath, crop, brightness: Number(slider.value) / 100 }) });
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : "Не удалось сохранить фото.");
      const card = trigger.closest(".photo-manage-card");
      card.querySelector("img.photo").src = payload.url;
      const link = card.querySelector("a.photo-link");
      if (link) {
        const url = new URL(link.href); url.searchParams.set("path", payload.path); link.href = url.href;
        link.dataset.lightboxSrc = payload.url;
      }
      document.querySelectorAll(`.reward-edit-main input[name="${field}"]`).forEach((input) => { input.value = payload.path; });
      trigger.dataset.photoPath = payload.path;
      setBusy(false); close();
      if (payload.cleanup_warning) {
        const warning = card.querySelector("[data-photo-source-error]");
        warning.textContent = "Фото сохранено. Старый файл не удалось удалить."; warning.hidden = false;
      }
    } catch (failure) { fail(failure.message || "Не удалось сохранить фото. Повторите попытку."); }
    finally { setBusy(false); }
  });
})();
