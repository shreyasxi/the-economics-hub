"""MoSPI TLS compatibility is host-specific and preserves certificate checks."""
import ssl
import unittest
from unittest.mock import Mock

import requests
from data.fetchers import mospi_http as http


class MospiHTTPTests(unittest.TestCase):
    def test_standard_https_success_needs_no_adapter(self):
        session = Mock()
        response = session.get.return_value
        self.assertIs(http.get(session, http.API_PREFIX+'catalogue', timeout=15), response)
        session.mount.assert_not_called()

    def test_legacy_handshake_retries_once_with_verified_host_scoped_context(self):
        session = requests.Session()
        response = Mock()
        session.get = Mock(side_effect=[requests.exceptions.SSLError(
            '[SSL: UNSAFE_LEGACY_RENEGOTIATION_DISABLED]'), response])
        self.assertIs(http.get(session, http.API_PREFIX+'catalogue', timeout=15), response)
        self.assertEqual(session.get.call_count, 2)
        adapter = session.get_adapter(http.API_PREFIX+'download')
        self.assertIsInstance(adapter, http.MospiAPIAdapter)
        self.assertEqual(adapter.context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(adapter.context.check_hostname)
        self.assertTrue(adapter.context.options & 0x4)
        self.assertNotIsInstance(session.get_adapter('https://www.mospi.gov.in/'), http.MospiAPIAdapter)
        self.assertNotIsInstance(session.get_adapter('https://api.mospi.gov.in.evil.example/'), http.MospiAPIAdapter)
        self.assertIs(adapter.poolmanager.connection_pool_kw['ssl_context'], adapter.context)
        proxy = adapter.proxy_manager_for('http://localhost:8080')
        self.assertIs(proxy.connection_pool_kw['ssl_context'], adapter.context)
        session.close()

    def test_certificate_and_other_host_errors_are_not_retried(self):
        for url, error in [(http.API_PREFIX, 'CERTIFICATE_VERIFY_FAILED'),
                           ('https://other.example/', 'UNSAFE_LEGACY_RENEGOTIATION_DISABLED'),
                           ('https://api.mospi.gov.in:8443/', 'UNSAFE_LEGACY_RENEGOTIATION_DISABLED')]:
            with self.subTest(url=url, error=error):
                session = Mock()
                session.get.side_effect = requests.exceptions.SSLError(error)
                with self.assertRaises(requests.exceptions.SSLError):
                    http.get(session, url)
                session.get.assert_called_once()
                session.mount.assert_not_called()

    def test_failed_retry_propagates(self):
        session = Mock()
        session.get.side_effect = [requests.exceptions.SSLError(
            'UNSAFE_LEGACY_RENEGOTIATION_DISABLED'), requests.exceptions.SSLError('still failed')]
        with self.assertRaisesRegex(requests.exceptions.SSLError, 'still failed'):
            http.get(session, http.API_PREFIX)
        self.assertEqual(session.get.call_count, 2)


if __name__ == '__main__':
    unittest.main()
