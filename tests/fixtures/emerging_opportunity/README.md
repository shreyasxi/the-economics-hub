# Consumer Services parser regression fixtures

Immutable September 2026 NSDL report, TRENT September 2026 XBRL and ARVINDFASN
September 2025 XBRL, copied losslessly from official source archives. `snapshot.json`
freezes the initial normalized research observations for comparison tests; it omits
archive receipts and its digest because it is a test fixture, not a publishable snapshot.
The test against the live committed store separately checks every normalized ownership
observation against its archived filing, and validates all source/snapshot checksums.
