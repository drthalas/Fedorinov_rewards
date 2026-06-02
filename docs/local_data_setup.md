# Local Data Setup

Use an environment variable to point the new application at the local legacy data folder during development:

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

## Development Sample Data vs Owner Production Data

The current development sample data folder is:

```text
/Users/hermes/Desktop/Rewards
```

This path is only for local development and testing. It must not be treated as a permanent application path.

The owner's production data will be selected locally on the owner's computer. The real owner database, photos, generated files, and local configuration remain outside Git and outside cloud storage unless the owner explicitly chooses another workflow.

Never hardcode the development sample path into business logic. For the first web mirror stage, `.env` and `REWARDS_DATA_DIR` are acceptable. Future local installations should use a DataSourceManager and a settings screen to save the selected data directory in local config.

Never commit real owner data.

Real local data must not be committed to this repository. This includes SQLite files, photos, PDFs, archives, executable files, DLLs, copied legacy folders, `.env` files, keys, tokens, and generated output containing personal data.
