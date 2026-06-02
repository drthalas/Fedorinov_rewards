# Project Overview

Fedorinov_rewards is a modernization project for the legacy WinForms application Rewards / "Nagrady".

The target is to move the old local Windows workflow into a browser-based interface. The first product milestone is a web mirror of the current functionality. Improvements should come later, after the existing UI, database, media folders, and export behavior are mapped safely.

At this stage, the project is limited to environment preparation, documentation, a read-only FastAPI skeleton, and local diagnostics.

The SQLite database and real photo files remain local. They must not be copied into this repository or committed to GitHub.

The first stage is read-only:

- inspect the old database without writes;
- validate that media folders are reachable;
- avoid printing personal data in reports;
- avoid changing `/Users/hermes/Desktop/Rewards`;
- avoid running old executable files.
