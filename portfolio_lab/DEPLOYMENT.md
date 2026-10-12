# Portfolio Lab deployment

The release uses private, immutable snapshot delivery. Market histories, source
evidence, old preparation runs and packages remain excluded from public Git.
The owner uploads the package to private HTTPS storage and configures secrets;
the application does not retrieve market histories from Yahoo/FRED/NSE on reruns.
Private delivery addresses transport and storage, not source licensing. The
source permissions recorded in the research notes remain a separate obligation.

## Initial upload

The prepared release is `output/portfolio_lab/release.portfolio-snapshot.zip`.
Its SHA-256 is in the adjacent `.zip.sha256` file. It includes only the active
Global, macro and India snapshots, their manifests and validation evidence.

1. Upload that ZIP to your private storage. Use a direct HTTPS download URL
   returning the ZIP with HTTP 200; login pages and redirects are rejected.
   The server needs access after restarts. A short-lived signed URL must be
   renewed before it expires; prefer an appropriately secured durable URL.
2. In Streamlit Cloud → app settings → Secrets, add the following top-level
   entries, replacing the placeholders with your URL and the exact checksum:

   ```toml
   PORTFOLIO_SNAPSHOT_URL = "https://your-private-storage.example/portfolio-snapshot.zip"
   PORTFOLIO_SNAPSHOT_SHA256 = "paste-the-64-character-sha256-here"
   ```

   [streamlit.example.toml](streamlit.example.toml) contains the exact checksum
   for the supplied package. Preserve existing application secrets. Never
   commit the real URL or token.
3. Add the same two values as GitHub repository Actions secrets to run
   **Portfolio Deployment Checks**. That workflow checks the actual deployment
   package and both modes; it does not upload data artifacts or commit histories.
4. Reboot the Streamlit application and open `/portfolio-lab`. Enter each mode
   and verify the dates, builder, comparison, research views and India SIP.

On the first visit to an investor mode, one cached download checks the pinned
ZIP checksum, file inventory, individual hashes and existing source/numerical
contracts. All three bundles activate with one atomic pointer. Updates retain
previous validated data on failure. A fresh server with no valid package shows
an unavailable-data notice; no fabricated or synthetic results are substituted.

## Refreshing the package

Use the existing environment from the owner’s source checkout, separate from
the server’s installed deployment data, at the repository root:

```sh
.venv/bin/python -m data.fetchers.portfolio_prices --prepare
.venv/bin/python -m data.fetchers.portfolio_macro
.venv/bin/python -m data.fetchers.portfolio_india --collect --prepare
.venv/bin/python -m portfolio_lab.deployment --validate
.venv/bin/python -m portfolio_lab.deployment --export output/portfolio_lab/release.portfolio-snapshot.zip
```

Run the India dashboard workflow first when refreshed official NSE TRI history
is needed, then update your local checkout before preparing India. Existing
source freshness and identity checks remain mandatory. Preparation failures
retain prior active source bundles; do not publish a partially refreshed release.

Upload under a new immutable object name, update **both** secrets together in
Streamlit and GitHub, run Portfolio Deployment Checks, then reboot Streamlit.
Snapshot refresh is explicit; the existing chart generators do not regenerate
or upload private Portfolio Lab data. No private market-data refresh schedule
is introduced by this release.

## Offline installation verification

```sh
.venv/bin/python -m portfolio_lab.deployment --install output/portfolio_lab/release.portfolio-snapshot.zip --sha256 YOUR_SHA256 --root /tmp/portfolio-clean-install --validate
```

Git tracks the application, deployment code, configuration examples and tests.
It deliberately ignores `data/stores/portfolio_lab/` and private ZIPs/checksums.
Removing those ignores would publicly distribute complete source histories and
is unnecessary for this deployment design.
