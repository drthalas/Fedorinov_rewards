# Roadmap

## Stage 0: Environment and Diagnostics

Create repository structure, documentation, read-only local data checks, and backend skeleton.

## Stage 1: Legacy UI and Database Map

Map legacy screens, database tables, fields, relationships, and workflows without changing the old application data.

## Stage 2: Read-Only Web Mirror

Build a browser interface that mirrors the old interface and reads from the existing SQLite database.

## Stage 3A: Writable-Mode Foundation

Create writable-mode configuration, write connection guardrails, audit logging, and the legacy feature gap map.

## Stage 3B: Person CRUD

Add person create/edit/delete with normal writable-mode checks and entity-integrity protections.

## Stage 3C: Reward CRUD

Add reward create/edit/delete with duplicate validation and protected media handling.

## Stage 3D: Mark CRUD

Add standalone mark create/edit/delete with duplicate validation and protected media handling.

## Stage 3E: Guides CRUD

Add rank and hierarchical guide editing, including validation for records that reference guide rows.

## Stage 3F: Photo Upload / Replace / Delete

Add controlled media upload, replacement, and deletion workflows for `Source/` and `SourceMark/`.

## Stage 3G: PDF Export

Recreate legacy person and summary PDF exports after read/write data workflows are stable.

## Stage 3H: Legacy Filters / Svod

Recreate legacy filters, summary tables, and export-adjacent views.

## Stage 4: Full Functional Mirror QA

Validate functional parity against the old WinForms application on the safe development data root.

## Stage 5: Local Deployment and Tunnel

Package the local server workflow and optionally expose it through a controlled tunnel.

## Stage 6: Improved UX and AI-Assisted Features

Improve usability after the web mirror is stable, then add AI-assisted workflows where they are useful and safe.
