"""Data cutoff and refresh status for the existing Portfolio Lab header."""
from datetime import datetime, timedelta, timezone
from html import escape
import json
from pathlib import Path
from zoneinfo import ZoneInfo

REFRESH_HOUR = 10
REFRESH_MINUTE = 45
REFRESH_WEEKDAYS = (2, 5)  # Wednesday, Saturday; Python Monday = 0.
GRACE_HOURS = 6


def latest_due(now):
    now = now.astimezone(timezone.utc)
    for offset in range(8):
        slot = (now - timedelta(days=offset)).replace(
            hour=REFRESH_HOUR, minute=REFRESH_MINUTE, second=0, microsecond=0)
        if slot.weekday() in REFRESH_WEEKDAYS and slot + timedelta(hours=GRACE_HOURS) <= now:
            return slot
    raise ValueError('No scheduled slot found')


def update_delayed(checked_at, now=None):
    """Allow scheduler/source delay before flagging a missed publication."""
    now = now or datetime.now(timezone.utc)
    checked = datetime.fromisoformat(checked_at.replace('Z', '+00:00'))
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    return checked < latest_due(now)


def _day(value):
    return datetime.fromisoformat(str(value)).strftime('%d %b %Y')


def data_timing_text(latest, manifest, reference_date=None):
    """Supporting source dates belong in the existing methodology section."""
    parts = ['Market prices through ' + _day(latest)]
    if reference_date:
        parts.append('Weekly calculation cutoff ' + _day(reference_date))
    if manifest.get('fx_latest'):
        parts.append('FX through ' + _day(manifest['fx_latest']))
    parts.append('Auto refresh scheduled for Wednesday and Saturday at 16:15 IST')
    return ' · '.join(parts)


def banner_html(latest, root, manifest, reference_date=None, now=None):
    """Show the usable analysis cutoff and successful update time, without live I/O."""

    lines = []
    checked = manifest.get('retrieved_utc')
    receipt = Path(root) / 'refresh.json'
    try:
        if receipt.exists():
            checked = json.loads(receipt.read_text())['checked_utc']
        if checked:
            updated = datetime.fromisoformat(checked.replace('Z', '+00:00'))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            lines.append('Updated ' + updated.astimezone(ZoneInfo('Asia/Kolkata')).strftime('%d %b · %H:%M IST'))
            if update_delayed(checked, now):
                lines.append('Update delayed · previous validated release')
    except (OSError, ValueError, KeyError, TypeError):
        lines.append('Refresh status unavailable')
    extra = ''.join('<span class="pl-refresh-line">' + escape(line) + '</span>' for line in lines)
    return ('<div class="rbi-head-meta pl-refresh-meta">'
            '<span class="pl-analysis-cutoff">Analysis through <strong>'
            + escape(_day(reference_date or latest)) + '</strong></span>' + extra + '</div>')
