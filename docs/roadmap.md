# Roadmap

## Stage 0: Environment and Diagnostics

Create repository structure, documentation, read-only local data checks, and backend skeleton.

## Stage 1: Legacy UI and Database Map

Map legacy screens, database tables, fields, relationships, and workflows without changing the old application data.

## Stage 2: Read-Only Web Mirror

Build a browser interface that mirrors the old interface and reads from the existing SQLite database.

## Stage 3: Photo Gallery and Search

Add safe media browsing, search, and filtering over local photo folders.

## Stage 4: PDF Export

Recreate export behavior and validate output against legacy expectations.

## Stage 5: Editing with Backups

Introduce edits only after backup, rollback, and validation workflows are implemented.

## Stage 6: Local Deployment and Tunnel

Package the local server workflow and optionally expose it through a controlled tunnel.

## Stage 7: Improved UX and AI-Assisted Features

Improve usability after the web mirror is stable, then add AI-assisted workflows where they are useful and safe.
