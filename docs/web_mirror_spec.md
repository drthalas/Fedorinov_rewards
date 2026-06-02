# Web Mirror Spec

The Stage 2 web mirror is read-only. It must not write to SQLite, copy media, delete files, create exports, or open local applications.

## `/` - Dashboard

- Purpose: Overview of local data availability and collection counts.
- Legacy forms covered: Form1 summary sections.
- Tables read: `person`, `rewards`, `mark`, `guide`, `guide_lev_0` through `guide_lev_4`.
- Fields shown: Counts, read-only status, database/media availability, aggregate reward/mark counts and price totals where safe.
- Photos shown: None by default.
- Data hidden on first stage: Names, links, comments, log rows.
- Read-only actions: Navigate to lists and diagnostics.
- Deferred: CSV/PDF export, activation status workflow, editing.

## `/persons` - Awarded Persons List

- Purpose: Browse awarded persons without opening the legacy application.
- Legacy forms covered: Form1 person list.
- Tables read: `person`, `guide`, `rewards`.
- Fields shown: Person id, rank label, reward count, photo presence flags.
- Photos shown: Optional safe thumbnail for `main_foto` only after media endpoint is implemented.
- Data hidden on first stage: Full name by default unless protected display is enabled, birthday, links, comments, document photos.
- Read-only actions: Filter, sort, open person detail.
- Deferred: Add/edit/delete person and bulk export.

## `/persons/{id}` - Awarded Person Card

- Purpose: Show one person and related rewards in a browser.
- Legacy forms covered: Form1 selected person panel, Form2 person detail.
- Tables read: `person`, `guide`, `rewards`, `guide_lev_0` through `guide_lev_3`.
- Fields shown: Person id, rank label, reward count, safe reward table, media presence, optional protected metadata block.
- Photos shown: `main_foto`, `person_foto`, `rewards_foto`, book/card thumbnails through safe media endpoint.
- Data hidden on first stage: Links and comments unless placed in protected block; raw filesystem paths.
- Read-only actions: Navigate to reward details and photo gallery.
- Deferred: Person editing, reward editing, photo upload, folder opening, PDF export.

## `/persons/{id}/photos` - Person Photo Gallery

- Purpose: Show all media linked to one person and their rewards.
- Legacy forms covered: Form1 all-photos viewer, Form2 all-photos viewer, Form4.
- Tables read: `person`, `rewards`, `guide_lev_3`.
- Fields shown: Image labels, photo type, associated reward id/name label.
- Photos shown: Person photos, group reward photo, book/card photos, reward front/back/book/reward-list photos.
- Data hidden on first stage: Raw paths and external links.
- Read-only actions: View thumbnails and larger image preview.
- Deferred: Upload, delete, rotate, rename, copy, PDF inclusion settings.

## `/rewards/{id}` - Reward Card

- Purpose: Show one person-attached reward.
- Legacy forms covered: Form1 selected reward grid, Form2 reward grid, Form3 reward edit dialog.
- Tables read: `rewards`, `person`, `guide`, `guide_lev_0` through `guide_lev_4`.
- Fields shown: Reward id, classification labels, number, stock state, purchase date, purchase/current price, media presence.
- Photos shown: `front_foto`, `back_foto`, `book1_foto`, `book2_foto`, `reward_list` through safe media endpoint.
- Data hidden on first stage: Person full name by default, source links, raw media paths.
- Read-only actions: Navigate to owning person and gallery.
- Deferred: Edit reward, duplicate-number validation, media upload, PDF export.

## `/marks` - Marks List

- Purpose: Browse standalone marks.
- Legacy forms covered: Form1 marks tab.
- Tables read: `mark`, `guide_lev_0` through `guide_lev_3`.
- Fields shown: Mark id, classification labels, number, stock state, purchase/current price, media presence.
- Photos shown: Optional front/back thumbnails through safe media endpoint.
- Data hidden on first stage: Link text and raw paths.
- Read-only actions: Filter, sort, open mark detail.
- Deferred: Add/edit/delete mark, CSV/PDF export.

## `/marks/{id}` - Mark Card

- Purpose: Show one standalone mark.
- Legacy forms covered: Form1 marks grid, Form3 mark edit dialog.
- Tables read: `mark`, `guide_lev_0` through `guide_lev_4`.
- Fields shown: Mark id, classification labels, number, stock state, purchase date, purchase/current price, media presence.
- Photos shown: `front_foto`, `back_foto`, `book1_foto`, `book2_foto`.
- Data hidden on first stage: Link text and raw media paths.
- Read-only actions: Navigate back to marks and guides.
- Deferred: Edit mark, media upload, local folder opening, PDF export.

## `/guides` - Tree Guide

- Purpose: Display the rank guide and hierarchical award/mark guide.
- Legacy forms covered: Form5, Form6.
- Tables read: `guide`, `guide_lev_0`, `guide_lev_1`, `guide_lev_2`, `guide_lev_3`, `guide_lev_4`.
- Fields shown: Guide hierarchy labels, IDs, child counts, reward/mark usage counts.
- Photos shown: None.
- Data hidden on first stage: Full link/source text from `guide_lev_4` unless protected display is enabled.
- Read-only actions: Expand/collapse tree, navigate to filtered rewards/marks.
- Deferred: Guide add/edit/delete and link backfill updates.

## `/search` - Search

- Purpose: Search across person, reward, and mark records.
- Legacy forms covered: Form1 reward search and mark search.
- Tables read: `person`, `rewards`, `mark`, `guide`, `guide_lev_3`.
- Fields shown: Result type, id, rank/classification label, number, stock state, safe snippets.
- Photos shown: Presence indicators or thumbnails only through safe media endpoint.
- Data hidden on first stage: Full comments, raw links, raw paths; full names should be protected by default.
- Read-only actions: Search by protected fields, open result detail pages.
- Deferred: CSV export and editing from result rows.

## `/health` - Environment Diagnostics

- Purpose: Verify read-only configuration and local data availability.
- Legacy forms covered: None directly; replaces unsafe startup side effects from `SQLite_Connection.ExistDB`.
- Tables read: Optional `select 1` only.
- Fields shown: Read-only flag, data directory exists, database exists, database readable, validation errors.
- Photos shown: None.
- Data hidden on first stage: Database contents and media paths beyond configured root.
- Read-only actions: Refresh diagnostics.
- Deferred: Repair/migration actions.

## `/settings/data-source` - Data Source Settings

- Purpose: Connect a local Rewards data folder for the current installation.
- Legacy forms covered: None directly; this is new infrastructure for local-first deployment.
- Tables read: Optional read-only database validation and safe aggregate diagnostics after the selected folder is checked.
- Fields shown: Current connected folder, input for a local Rewards folder path, validation status, read-only mode status.
- Photos shown: None directly; only media validation counts.
- Data hidden on first stage: Raw personal data, raw photo filenames, comments, links, and database row contents.
- Read-only actions: Enter or choose a folder path, check connection, save selected path in local config.
- Validation status:
  - `database/MyDatabase.sqlite` found or missing;
  - `Source/` found or missing;
  - `SourceMark/` found or missing;
  - `default/nofoto.jpg` found or missing;
  - photo links total/existing/missing;
  - read-only mode enabled.
- Deferred: Full OS-native file picker, data migrations, backups, editing, cloud sync, and any data upload.
