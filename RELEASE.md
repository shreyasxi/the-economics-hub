# Release and GitHub Actions order

All data-publishing workflows check out and push to the branch selected in
Actions. A feature-branch dispatch cannot push that branch's commits to `main`.
Publishing jobs share a per-branch concurrency group; run the initial release
sequence one workflow at a time and wait for success before proceeding.

First configure the private Portfolio snapshot as described in
[Portfolio deployment](portfolio_lab/DEPLOYMENT.md). Existing workflows need
`FRED_API_KEY` and RBI Sentinel needs `ANTHROPIC_API_KEY`; Portfolio Deployment
Checks needs `PORTFOLIO_SNAPSHOT_URL` and `PORTFOLIO_SNAPSHOT_SHA256`.

## Before the production merge

Run **Repository Checks** and **Portfolio Deployment Checks** on the release
branch. Repository Checks exercises all source tests on Python 3.11; the second
workflow downloads and tests the actual private deployment package, including
the real-data independent verifiers. Local private data are absent from normal
CI, so the additional workflow is required to verify the full Lab deployment.

You can test chart workflows on the release branch too. Their resulting data
commits stay on that branch and must be included in the eventual merge. Do not
run a release-branch generator while merging that branch.

## Initial production run

After merging the release branch to `main`, select **main** for every dispatch:

1. **Repository Checks** — verify the merged application and source contracts.
2. **RBI Sentinel** — update saved MPC documents, meeting facts and summaries.
3. **India Dashboard Generator** — full fetch (`skip_fetch=false`), with emergency
   manual CPI/IIP fallbacks left false. This publishes India data used by World.
4. **RBI Monetary Conditions Daily** — refresh the two latest monetary charts.
5. **Headline Collector** — populate the headline cache before Weekly Markets.
6. **Weekly Markets Generator** — publish markets, matrix, news and signals.
7. **World Generator** — publish all World panels and the shared snapshot,
   including inflation breadth, banking liquidity, CFNAI, NFCI, CISS, European
   sectors, yields and supply-chain pressure.
8. **Central Bank Rates** — exercise the between-edition rate refresh.
9. **Global Yields Monday Retry** — exercise the standalone yield refresh.
10. **Portfolio Deployment Checks** — validate the uploaded private package and
    both investor modes against the merged app. Generators above do not refresh
    this private package; upload a new package separately when desired.
11. **Keep Streamlit App Alive** — exercise the deployed app wake-up/visit.

Headline Collector and Weekly can run before the RBI/India sequence if desired;
the dependency is Collector → Weekly. The important economic dependency is
RBI Sentinel → India → World, then the two World refresh workflows. Keep Alive
checks page access, not the full business logic or chart content.

## Completion criteria

Stop at a failed required workflow, read its failing step, fix it and rerun.
Green runs may contain optional-source omissions; inspect the India source
steps and the published page before accepting the release. World deliberately
fails publication when its required sources fail, rather than publish a
partially validated edition. A failed refresh must not be treated as success.

Finally reboot Streamlit if needed and inspect Weekly, World, India, RBI,
the archive, Research & About and both Portfolio modes. Confirm the new World
sections exist in `assets/macro/<edition>/`, not only in ignored local `output/`.
