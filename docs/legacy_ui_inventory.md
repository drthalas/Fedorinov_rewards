# Legacy UI Inventory

This inventory is based on read-only review of `Form1.cs`, `Form1.Designer.cs`, `Form2.cs`, `Form3.cs`, `Form5.cs`, `Form6.cs`, `Form7.cs`, and `Form8.cs` in `legacy/_external/rewards`. It describes UI behavior and avoids real local data contents.

## Main tab: Награды

- left panel: `groupBox1` with `listBox1`, titled `ФИО награжденных (N)`, loaded from `person order by id`.
- toolbar: guide button `button23`, add person `button2`, edit person `button3`, delete person `button4`.
- right panel: selected person reward grid `dataGridView3` with reward id, name, number, current price, stock flag, front/back images, and link text.
- lower blocks: person reward totals `dataGridView2`, links/comment grid `dataGridView4`, selected person's main photo `pictureBox1`.
- buttons/actions: create person via `Form2("add")`, edit person via `Form2("edit")`, delete person and related rewards/media, open guide tree via `Form6`, generate person booklet via `CreatePDF`, create ZIP of person media, open all photos via `Form4`.
- current web equivalent: `/legacy?tab=rewards`, `/persons`, `/persons/{id}`, `/persons/{id}/photos`, `/persons/new`, `/persons/{id}/edit`, `/persons/{id}/delete`, `/persons/{id}/rewards/new`, `/rewards/{id}`, `/rewards/{id}/edit`, `/rewards/{id}/delete`, `/guides`.
- missing: true desktop modal behavior, media folder open/zip export, person PDF booklet, inline image viewer/lightbox parity.
- write/unsafe actions: add/edit/delete person, add/edit/delete reward, media folder deletion/copy, PDF/ZIP file generation.
- safe links/buttons now: guide link, existing CRUD forms when `WRITE_MODE=true`, disabled CRUD controls when read-only, booklet button as disabled/deferred link.

## Tab: Поиск

- left/top controls: search text, criterion selectors for field and match mode.
- main panel: `dataGridView8` result grid loaded by `loadRewards`, grouped around reward rows with person context.
- buttons/actions: run search, refresh list, open/edit selected person from result row, open image viewer for image cells.
- current web equivalent: `/legacy?tab=search&q=...` and `/search`.
- missing: legacy field selector parity (`ФИО`, `Название`, `Номер`, `Звание`) and criterion parity (`Равно`, `Содержит`, `Начинается`).
- write/unsafe actions: opening result in `Form2("edit")` can mutate person/rewards in legacy.
- safe links/buttons now: grouped read-only search results for persons, rewards, and marks; result links navigate to existing web pages.

## Tab: Знаки

- left/main panel: standalone mark grid `dataGridView5` loaded from `mark`, with guide labels, number, stock, dates/prices, images, and link text.
- toolbar: add mark `button6`, edit mark `button7`, delete mark `button15`.
- lower block: mark totals `dataGridView7`.
- buttons/actions: create/edit mark through `Form3("addmark"/"editmark")`, delete mark and legacy media folder, open image viewer, open links.
- current web equivalent: `/legacy?tab=marks`, `/marks`, `/marks/{id}`, `/marks/new`, `/marks/{id}/edit`, `/marks/{id}/delete`.
- missing: exact legacy grid columns with inline images and full link opening behavior.
- write/unsafe actions: mark add/edit/delete and legacy SourceMark folder deletion.
- safe links/buttons now: mark list and selected mark card; existing guarded CRUD forms only when `WRITE_MODE=true`.

## Tab: Свод.таблица

- controls: reward/mark mode selector, stock filter, guide-level filters, CSV export button, PDF export button.
- main panel: generated `dataGridView6` with dynamic columns for reward/mark summary.
- buttons/actions: build summary, remove zero rows/columns, total rows, export CSV, configure PDF through `Form7` or `Form8`.
- current web equivalent: `/legacy?tab=summary` with basic counts, stock counts, and purchase/current price sums.
- missing: guide filter cascade, dynamic matrix parity, CSV export, PDF export options and output.
- write/unsafe actions: CSV/PDF writes generated files outside DB; clicking rows opens edit forms in legacy.
- safe links/buttons now: read-only aggregate summary only.

## Tab: О программе

- main panel: activation/demo text in `richTextBox1`, activation code input, version and contact/license notes.
- buttons/actions: activation code write through `StringCipher`, demo mode messaging, program version display.
- current web equivalent: `/legacy?tab=about`.
- missing: activation/licensing workflow and exact legacy text.
- write/unsafe actions: activation secret update and legacy logs.
- safe links/buttons now: preview status, data directory, current commit, read-only/write-mode indicator, local-data warning.

## Add/edit forms

- `Form2`: person add/edit form with rank guide, birthday, links, comment, person photos, reward grid, reward add/edit/delete, all-photo view, folder open.
- `Form3`: reward/mark add/edit form with guide cascade, number, stock, purchase date, purchase/current prices, link aggregation, photo add/delete controls.
- `Form5`: rank guide CRUD.
- `Form6`: hierarchical guide tree CRUD and `id_link` backfill into rewards/marks.
- `Form7`: reward summary PDF options.
- `Form8`: mark summary PDF options.

The web mirror currently routes person/reward/mark CRUD to existing guarded web forms. Guides CRUD, photo upload/replace/delete, PDF/CSV exports, activation, and local folder operations remain deferred.
