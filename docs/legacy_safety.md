# Legacy Safety

The legacy repositories are read-only references for analysis.

Legacy sources are cloned into `legacy/_external/`:

- `legacy/_external/rewards`
- `legacy/_external/activation-rewards`

No changes should be committed inside `legacy/_external/`. The directory is ignored by the main repository and must remain outside the new project history.

Do not push to the `erypalovyury/rewards` or `erypalovyury/activation-rewards` repositories. Their push URLs are disabled intentionally:

```text
origin DISABLED (push)
```

All new development happens only in `drthalas/Fedorinov_rewards`.

To refresh legacy source references, run:

```sh
scripts/fetch_legacy_sources.sh
```

The script clones or fetches the legacy repositories and then sets each legacy `origin` push URL to `DISABLED`.

Never copy real data, SQLite databases, media, PDFs, ZIP archives, EXE/DLL files, `.env` files, keys, tokens, or generated personal-data reports into Git.
