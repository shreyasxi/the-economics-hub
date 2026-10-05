"""MoSPI TLS compatibility is host-specific and preserves certificate checks."""
import ssl
import unittest
from unittest.mock import Mock, patch

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


    @patch.object(http.time, 'sleep')
    def test_gateway_failure_retries_then_returns_success(self, sleep):
        session = Mock()
        failed = Mock(status_code=502)
        recovered = Mock(status_code=200)
        session.get.side_effect = [failed, recovered]
        self.assertIs(http.get(session, http.API_PREFIX+'catalogue', params={'page': 1}, timeout=15), recovered)
        self.assertEqual(session.get.call_count, 2)
        self.assertEqual(session.get.call_args_list[0], session.get.call_args_list[1])
        failed.close.assert_called_once()
        sleep.assert_called_once_with(2)

    @patch.object(http.time, 'sleep')
    def test_persistent_server_failure_is_bounded_and_still_fails_status_check(self, sleep):
        session = Mock()
        failed = requests.Response()
        failed.status_code = 500
        failed._content = b'official server error'
        failed._content_consumed = True
        session.get.return_value = failed
        response = http.get(session, http.API_PREFIX+'iip')
        with self.assertRaises(requests.HTTPError):
            response.raise_for_status()
        self.assertEqual(session.get.call_count, 4)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [2, 4, 8])

    @patch.object(http.time, 'sleep')
    def test_connection_timeout_is_retried_but_certificate_failure_is_not(self, sleep):
        session = Mock()
        recovered = Mock(status_code=200)
        session.get.side_effect = [requests.Timeout('slow'), recovered]
        self.assertIs(http.get(session, http.API_PREFIX+'iip'), recovered)
        self.assertEqual(session.get.call_count, 2)
        session.get.reset_mock()
        session.get.side_effect = requests.exceptions.SSLError('CERTIFICATE_VERIFY_FAILED')
        with self.assertRaises(requests.exceptions.SSLError):
            http.get(session, http.API_PREFIX+'iip')
        session.get.assert_called_once()

    @patch.object(http.time, 'sleep')
    def test_permanent_status_and_unrelated_host_do_not_retry(self, sleep):
        for url, status in [(http.API_PREFIX+'iip', 404), ('https://other.example/', 502),
                            ('https://api.mospi.gov.in.evil.example/', 500)]:
            session = Mock()
            response = Mock(status_code=status)
            session.get.return_value = response
            self.assertIs(http.get(session, url), response)
            session.get.assert_called_once()
        sleep.assert_not_called()


if __name__ == '__main__':
    unittest.main()
