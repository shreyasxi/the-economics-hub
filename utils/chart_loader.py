"""
Economics Hub — Chart Loader
Discovers the latest chart folder and returns sorted PNG paths.

Resolution order:
  1. assets/  — git-tracked, used on Streamlit Cloud and after CI commits
  2. output/  — local dev fallback (git-ignored but exists on disk)

Both directories are checked so local development works without a CI commit.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Directory resolution
# ---------------------------------------------------------------------------

def _get_base_dirs() -> list[Path]:
    return [
        PROJECT_ROOT / "assets",
        PROJECT_ROOT / "output",
    ]


def _latest_folder(subdir: str) -> tuple[Path | None, str | None]:
    """
    Find the most recent dated subfolder across both base directories.

    Weekly:      subdir = "weekly",  folders named YYYY-MM-DD
    Macro/India: subdir = "macro" or "india", folders named YYYY-MM

    Returns (path, date_label) or (None, None) if nothing is found.
    """
    candidates: list[Path] = []
    for base in _get_base_dirs():
        p = base / subdir
        if not p.exists():
            continue
        for child in p.iterdir():
            if child.is_dir():
                candidates.append(child)

    if not candidates:
        return None, None

    # Lexicographic sort works for both YYYY-MM-DD and YYYY-MM formats
    latest = sorted(candidates, key=lambda x: x.name)[-1]
    return latest, latest.name


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_charts(subdir: str) -> tuple[list[Path], str | None]:
    """
    Return (sorted_png_list, date_label) for the latest folder under `subdir`.

    PNGs are sorted by natural order so that 10b_ sorts after 10_ and
    before 11_, handling the irregular numbering in the weekly pipeline.
    """
    folder, label = _latest_folder(subdir)
    if folder is None:
        return [], None

    pngs = sorted(
        folder.glob("*.png"),
        key=lambda p: _natural_sort_key(p.name),
    )
    return pngs, label


def get_folder_mtime(subdir: str) -> datetime | None:
    """
    Return the modification time of the most recently modified PNG in the
    latest folder. Used to display "Last updated: YYYY-MM-DD HH:MM".
    """
    folder, _ = _latest_folder(subdir)
    if folder is None:
        return None

    pngs = list(folder.glob("*.png"))
    if not pngs:
        return None

    return datetime.fromtimestamp(max(p.stat().st_mtime for p in pngs))


def is_streamlit_cloud() -> bool:
    """
    Detect the Streamlit Cloud environment.

    On Streamlit Cloud, STREAMLIT_SHARING_MODE is set to "1".
    The IS_STREAMLIT_CLOUD flag can also be set manually in Streamlit
    Cloud secrets as a safety override.
    """
    return (
        os.environ.get("STREAMLIT_SHARING_MODE") == "1"
        or os.environ.get("IS_STREAMLIT_CLOUD", "").lower() == "true"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _natural_sort_key(filename: str) -> list:
    """
    Natural sort key that handles mixed alphanumeric prefixes correctly.
    Example sort order: 00_, 01_, ..., 10_, 10b_, 10c_, 11_, ...
    """
    parts = re.split(r"(\d+)", filename)
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def clean_title(filename: str) -> str:
    """
    Derive a human-readable chart title from a filename.
    '01_equities_weekly.png' → 'Equities Weekly'
    '10b_sector_rotation.png' → 'Sector Rotation'
    """
    stem = Path(filename).stem                    # strip .png
    stem = re.sub(r"^\d+[a-z]?_", "", stem)      # strip leading numeric prefix
    return stem.replace("_", " ").title()
