# Legacy UI Map

This map is based on read-only inspection of `legacy/_external/rewards`. It describes legacy behavior without exposing real database records.

## Form1 - Main Screen

- Purpose: Main application shell for persons, rewards, standalone marks, search, filtered summary tables, photo viewing, activation status, PDF export, CSV export, and guide access.
- Data shown: Person list, selected person reward list, selected person links/comment block, selected person main photo, global reward statistics, standalone mark list, search results, category-filtered summary grids, activation/help text.
- SQLite tables used: `person`, `rewards`, `mark`, `guide`, `guide_lev_0`, `guide_lev_1`, `guide_lev_2`, `guide_lev_3`, `guide_lev_4`, `logs`.
- Main UI blocks: Person list, selected person rewards grid, selected person metadata/link grid, standalone marks tab, global rewards search tab, guide filter controls, summary grid, activation/info tab.
- Legacy actions: Add/edit/delete person, add/edit/delete reward, add/edit/delete mark, open file folders, open external links, show photos, export person PDF, export summary PDF, export CSV, manage guides, enter activation code, write logs.
- Web mirror equivalent: Dashboard with counts, `/persons`, `/persons/{id}`, `/persons/{id}/photos`, `/marks`, `/marks/{id}`, `/search`, `/guides`, read-only summary views.
- Deferred actions for future editing stage: All insert/update/delete operations, activation handling, writing logs, folder creation/deletion, media copy, opening Explorer, PDF/CSV export, external link launching.

## Form2 - Person Add/Edit

- Purpose: Add or edit a person and the person's attached rewards and photos.
- Data shown: Person identity fields, rank, birthday, links, comment, person photos, main photo, group rewards photo, book/card photos, reward grid for that person.
- SQLite tables used: `person`, `rewards`, `guide`.
- Main UI blocks: Person details tab, person photo controls, rewards grid, reward add/edit/delete controls, all-photos viewer button, local folder button.
- Legacy actions: Insert/update `person`, insert/update/delete `rewards`, copy selected photos into `Source/{person_id}/`, open local person folder, manage rank guide through Form5, show images through Form4.
- Web mirror equivalent: `/persons/{id}` read-only detail page with rank, dates, protected links/comment block, reward list, and media thumbnails; `/persons/{id}/photos` gallery.
- Deferred actions for future editing stage: Person create/edit/delete, reward create/edit/delete, image upload/paste/copy, local folder opening, rank guide editing.

## Form3 - Reward/Mark Add/Edit

- Purpose: Add or edit a reward attached to a person, or add/edit a standalone mark.
- Data shown: Hierarchical guide selection, number, in-stock flag, purchase date, purchase price, current price, link field, reward/mark photos, reward list photo.
- SQLite tables used: `rewards`, `mark`, `guide_lev_0`, `guide_lev_1`, `guide_lev_2`, `guide_lev_3`, `guide_lev_4`.
- Main UI blocks: Cascading guide selectors, link selector/list, numeric fields, stock/date/price controls, photo controls for front/back/book/reward-list images.
- Legacy actions: Validate duplicate number by name, insert/update `mark`, update reward rows through parent grid, copy media to `Source/` or `SourceMark/`, manage hierarchical guides through Form6, open local media folders.
- Web mirror equivalent: `/rewards/{id}` and `/marks/{id}` read-only detail pages showing classification, number, stock state, dates/prices, protected link block, and media thumbnails.
- Deferred actions for future editing stage: Save reward/mark, media upload/copy/delete, duplicate validation workflow, guide editing, local folder opening.

## Form4 - Image Viewer

- Purpose: Modal image viewer for one image or an image collection.
- Data shown: Selected image, optional image label, collection position.
- SQLite tables used: None directly; receives in-memory photo objects from other forms.
- Main UI blocks: Large image area, previous/next controls, image label.
- Legacy actions: Cycle images by buttons or image click.
- Web mirror equivalent: Gallery route or lightbox-style viewer in `/persons/{id}/photos`, `/rewards/{id}`, and `/marks/{id}`.
- Deferred actions for future editing stage: None for writes; keep only local media read access with safe path resolution.

## Form5 - Rank Guide

- Purpose: Manage the rank guide used by person records.
- Data shown: List of rank guide entries.
- SQLite tables used: `guide`.
- Main UI blocks: List box, text input, add/update button, edit/delete context menu.
- Legacy actions: Insert/update/delete rows in `guide`.
- Web mirror equivalent: `/guides` read-only rank section.
- Deferred actions for future editing stage: Rank create/edit/delete and validation.

## Form6 - Hierarchical Guide Editor

- Purpose: Manage the hierarchical award/mark guide tree.
- Data shown: Tree of `guide_lev_0` through `guide_lev_4`.
- SQLite tables used: `guide_lev_0`, `guide_lev_1`, `guide_lev_2`, `guide_lev_3`, `guide_lev_4`, plus updates to `rewards.id_link` and `mark.id_link` when link nodes change.
- Main UI blocks: Tree view, root/add/edit/delete context menus.
- Legacy actions: Insert/update/delete guide nodes, recursively load tree, aggregate level-4 links back into rewards/marks.
- Web mirror equivalent: `/guides` read-only tree with levels for state/country, category, subcategory, name, and related links.
- Deferred actions for future editing stage: All tree mutations and backfill updates to rewards/marks.

## Form7 - Reward Summary PDF Options

- Purpose: Configure PDF summary export for person-attached rewards.
- Data shown: Sort choice and checkbox options for included columns.
- SQLite tables used: None directly; Form1 uses selected options to query `rewards` and `person`.
- Main UI blocks: Sort radio buttons and column checkboxes for number, reward photos, card photos, book photos, reward list, name, and person name.
- Legacy actions: Select columns and sort order, then Form1 generates PDF through `CreatePDF`.
- Web mirror equivalent: Future export configuration, not part of the Stage 2 read-only mirror.
- Deferred actions for future editing stage: PDF export and export options.

## Form8 - Mark Summary PDF Options

- Purpose: Configure PDF summary export for standalone marks.
- Data shown: Sort choice and checkbox options for included columns.
- SQLite tables used: None directly; Form1 uses selected options to query `mark`.
- Main UI blocks: Sort radio buttons and column checkboxes for name, current price, number, photos, and book photos.
- Legacy actions: Select columns and sort order, then Form1 generates PDF through `CreatePDF`.
- Web mirror equivalent: Future mark export configuration, not part of the Stage 2 read-only mirror.
- Deferred actions for future editing stage: PDF export and export options.

## Supporting Classes

- `SQLite_Connection.cs`: Creates and mutates the legacy SQLite schema, runs queries, writes logs. The new backend must not reuse its write behavior; it should keep `mode=ro`.
- `CreatePDF.cs`: Builds person and summary PDF exports using person, reward, mark, link, comment, and photo data. Stage 2 should not recreate export yet.
- `StringCipher.cs`: Handles activation secret encryption/decryption. Activation is not part of the new read-only web mirror.
- `Environment.cs`: Holds local media folders and simple value objects used by forms.
