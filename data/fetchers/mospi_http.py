"""Verified HTTPS requests with a narrowly scoped MoSPI legacy-server retry."""
import logging
import ssl
import time
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context


API_PREFIX = 'https://api.mospi.gov.in/'
LOG = logging.getLogger(__name__)


class MospiAPIAdapter(HTTPAdapter):
    """Allow MoSPI's legacy server handshake while retaining certificate checks."""

    def __init__(self):
        self.context = create_urllib3_context()
        # OpenSSL's SSL_OP_LEGACY_SERVER_CONNECT is bit 2. Python exposes its
        # named constant only in newer releases, including Python 3.12+.
        self.context.options |= getattr(ssl, 'OP_LEGACY_SERVER_CONNECT', 0x4)
        super().__init__()

    def init_poolmanager(self, connections, maxsize, block=False, **kwargs):
        kwargs['ssl_context'] = self.context
        return super().init_poolmanager(connections, maxsize, block, **kwargs)

    def proxy_manager_for(self, proxy, **kwargs):
        kwargs['ssl_context'] = self.context
        return super().proxy_manager_for(proxy, **kwargs)


def _get_once(session, url, **kwargs):
    """Retry only the known MoSPI legacy-handshake error, once, on that host."""
    try:
        return session.get(url, **kwargs)
    except requests.exceptions.SSLError as exc:
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.hostname != 'api.mospi.gov.in'
                or parsed.port not in (None, 443)
                or 'UNSAFE_LEGACY_RENEGOTIATION_DISABLED' not in str(exc)):
            raise
        LOG.warning('Retrying MoSPI API with legacy-server TLS compatibility; '
                    'certificate verification remains enabled')
        session.mount(API_PREFIX, MospiAPIAdapter())
        return session.get(url, **kwargs)


RETRY_STATUSES = {429, 500, 502, 503, 504}
RETRY_DELAYS = (2, 4, 8)


def get(session, url, **kwargs):
    """Retry transient official MoSPI GET failures without weakening validation.

    At most four HTTP attempts; certificate errors and other hosts fail without
    backoff. Return the final HTTP response so callers retain normal status and
    payload checks. No cached source or substitute series is introduced.
    """
    parsed = urlsplit(url)
    official = (parsed.scheme == 'https' and parsed.hostname in
                ('api.mospi.gov.in', 'www.mospi.gov.in', 'mospi.gov.in')
                and parsed.port in (None, 443))
    if not official:
        return _get_once(session, url, **kwargs)
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            response = _get_once(session, url, **kwargs)
        except requests.exceptions.SSLError:
            raise  # Only the narrowly scoped compatibility path may retry TLS.
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            if attempt == len(RETRY_DELAYS):
                raise
            reason = type(exc).__name__
        else:
            if getattr(response, 'status_code', None) not in RETRY_STATUSES or attempt == len(RETRY_DELAYS):
                return response
            reason = 'HTTP ' + str(response.status_code)
            response.close()
        delay = RETRY_DELAYS[attempt]
        LOG.warning('MoSPI %s for %s; retry %d/%d in %ds',
                    reason, url, attempt + 1, len(RETRY_DELAYS), delay)
        time.sleep(delay)
