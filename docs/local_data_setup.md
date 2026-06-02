# Local Data Setup

Use an environment variable to point the new application at the local legacy data folder:

```sh
REWARDS_DATA_DIR=/Users/hermes/Desktop/Rewards
```

Expected database path:

```text
database/MyDatabase.sqlite
```

Expected media and support folders:

- `Source/`
- `SourceMark/`
- `default/nofoto.jpg`
- `default/times.ttf`

The full resolved database path is:

```text
/Users/hermes/Desktop/Rewards/database/MyDatabase.sqlite
```

Real local data must not be committed to this repository. This includes SQLite files, photos, PDFs, archives, executable files, DLLs, copied legacy folders, `.env` files, keys, tokens, and generated output containing personal data.
