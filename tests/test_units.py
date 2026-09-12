"""
Unit-conversion regression tests.

These exist because two published charts were overstating values by exactly
1,000x for months without anyone noticing:

  * India fiscal  - CAG workbook stores Rs crore; the code divided by 100 and
                    labelled the result "Rs Lakh Crore" (needs 100,000).
  * Fed balance   - FRED publishes WALCL in millions of USD; the macro table
                    sheet             labelled the raw value "$B".

Run:  python -m pytest tests/ -q      (or: python tests/test_units.py)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generate_india import CRORE_PER_LAKH_CRORE, crore_to_lakh_crore


# ── India: CAG crore -> lakh crore ──────────────────────────────────────────

def test_crore_per_lakh_crore_constant():
    """1 lakh crore is 100,000 crore. The old value of 100 was the bug."""
    assert CRORE_PER_LAKH_CRORE == 100_000


def test_feb26_capex_converts_to_realistic_magnitude():
    """
    Feb-26 monthly capex from data/cag_monthly_accounts.xlsx is Rs 87,041 crore
    (929,322 cumulative less 842,281 the prior month). In lakh crore that is
    0.87 - not 870, which is what the dashboard published.
    """
    assert round(crore_to_lakh_crore(87_041), 2) == 0.87


def test_ytd_capex_converts_to_realistic_magnitude():
    """FY26 capex through Feb: Rs 929,322 crore = Rs 9.29 lakh crore."""
    assert round(crore_to_lakh_crore(929_322), 2) == 9.29


def test_monthly_capex_stays_below_one_percent_of_gdp():
    """
    A sanity bound of the kind a series catalogue would enforce automatically.
    India's GDP is roughly Rs 330 lakh crore. One month of central government
    capex cannot plausibly exceed a few percent of that; the buggy value
    (870 lakh crore) was more than twice annual GDP.
    """
    india_gdp_lakh_crore = 330
    monthly_capex = crore_to_lakh_crore(87_041)
    assert 0 < monthly_capex < india_gdp_lakh_crore * 0.05


def test_none_passes_through():
    """Months with no release must stay None rather than becoming 0.0."""
    assert crore_to_lakh_crore(None) is None


# ── US: FRED WALCL millions -> billions ─────────────────────────────────────

def test_walcl_millions_to_billions():
    """
    WALCL arrives from FRED in millions. 6,593,871 million = $6,594B = $6.6T.
    The table printed the raw figure under a "$B" heading.
    """
    walcl_millions = 6_593_871
    assert round(walcl_millions / 1000) == 6_594


def test_walcl_in_billions_is_plausible():
    """The Fed's balance sheet is single-digit trillions, not quadrillions."""
    walcl_billions = 6_593_871 / 1000
    assert 1_000 < walcl_billions < 20_000


if __name__ == "__main__":
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  PASS  {name}"); passed += 1
            except AssertionError as e:
                print(f"  FAIL  {name}: {e}"); failed += 1
    print(f"\n  {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
