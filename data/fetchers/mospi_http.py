"""Verified HTTPS requests with a narrowly scoped MoSPI legacy-server retry."""
import logging
import ssl
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


def get(session, url, **kwargs):
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
