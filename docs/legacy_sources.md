# Legacy Sources

The new project must not mix legacy WinForms code directly into the modernized codebase.

Legacy repositories used for analysis:

- Main legacy repository: `https://github.com/erypalovyury/rewards`
- Activation legacy repository: `https://github.com/erypalovyury/activation-rewards`

Local test data folder:

```text
/Users/hermes/Desktop/Rewards
```

Known local contents include:

- `database/MyDatabase.sqlite`
- `Source/`
- `SourceMark/`
- `default/`
- `itextsharp.dll`
- `runtimes/`
- old executable and DLL files

Real data cannot be committed. This includes databases, photos, generated PDFs, binaries, archives, source folders copied from the old application, `.env` files, tokens, and keys.

Use `scripts/fetch_legacy_sources.sh` to clone legacy sources into `legacy/_external/`. That directory is ignored by git.
