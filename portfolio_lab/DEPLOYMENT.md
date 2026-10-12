# Portfolio Lab deployment

Validated public datasets ship in Git under `data/published/portfolio_lab/`.
The owner confirmed permission to publish the source histories. Streamlit Cloud
receives Global, macro and India snapshots in a normal checkout: no external
storage, download URL or snapshot secrets are required. The app reads prepared
data; allocations and navigation do not trigger market-data downloads.

Each namespace has one CURRENT pointer, one immutable active bundle and its
source manifests/checksums. Source identity, corporate actions, calendars,
return conventions and currency alignment are validated by the existing loaders.
`deployment.json` records the complete published file inventory and hashes.
Local preparation runs and superseded snapshots remain in the ignored
`data/stores/portfolio_lab/` directory; only the active release is published.

## Validate a checkout

```sh
.venv/bin/python -m portfolio_lab.deployment --validate
.venv/bin/python -m pytest tests -q
```

Repository Checks and Portfolio Deployment Checks validate the same published
data in GitHub Actions. The latter also runs all four independent real-data
portfolio verifiers. No additional data secrets are needed for either workflow.

## Refresh and publish

Run these from the owner’s source checkout:

```sh
.venv/bin/python -m data.fetchers.portfolio_prices --prepare
.venv/bin/python -m data.fetchers.portfolio_macro
.venv/bin/python -m data.fetchers.portfolio_india --collect --prepare
.venv/bin/python -m portfolio_lab.deployment --publish --validate
.venv/bin/python -m pytest tests -q
```

Refresh the official NSE TRI history with the India workflow and update the
local checkout before preparing India when newer observations are needed.
Publish validates all three active bundles before replacing the public release.
A failure preserves the previous publication. Commit and push the changed
`data/published/portfolio_lab/` files together after validation passes.

On deployment, public snapshots are the default when local preparation data
are absent. Local development can continue to use its prepared source bundles.
No additional market-data refresh schedule has been introduced. Source dates,
provenance, stale-data notices and calculation assumptions remain visible.

See [RELEASE.md](../RELEASE.md) for the workflow order and production checks.
