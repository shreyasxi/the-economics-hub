"""One shared download per configured immutable deployment package."""
import os

import streamlit as st

from portfolio_lab.deployment import download


def settings():
    values = {}
    for name in ('PORTFOLIO_SNAPSHOT_URL', 'PORTFOLIO_SNAPSHOT_SHA256'):
        values[name] = os.environ.get(name, '')
        if not values[name]:
            try:
                values[name] = str(st.secrets.get(name, ''))
            except (FileNotFoundError, KeyError):
                pass
    return values


@st.cache_resource(show_spinner='Loading portfolio data…', max_entries=2)
def _install(url, digest):
    return download(url, digest)


def ensure_snapshot():
    config = settings()
    url, digest = config['PORTFOLIO_SNAPSHOT_URL'], config['PORTFOLIO_SNAPSHOT_SHA256']
    if not url and not digest:
        return
    if not url or not digest:
        st.warning('Portfolio data setup is incomplete. Please contact the site maintainer.')
        return
    try:
        _install(url, digest)
    except Exception:
        # Never expose signed URLs, provider errors or private filesystem paths.
        # An already validated deployment remains active after a failed update.
        st.warning('The portfolio data update is temporarily unavailable. Any previously validated data remain available.')
