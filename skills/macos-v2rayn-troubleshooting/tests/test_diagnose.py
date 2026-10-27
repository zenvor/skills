"""Offline regressions; no proxy, account, or system settings are changed."""
import http.server
import importlib.util
import io
import json
import pathlib
import socket
import tempfile
import threading
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'scripts/diagnose.py'
SPEC = importlib.util.spec_from_file_location('diagnose', SCRIPT)
diagnose = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnose)


class ImapTests(unittest.TestCase):
    def probe(self, data):
        raw = MagicMock()
        raw.__enter__.return_value = raw
        tls = MagicMock()
        tls.__enter__.return_value = tls
        tls.makefile.return_value = io.BytesIO(data)
        tls.version.return_value = 'TLSv1.3'
        context = MagicMock()
        context.wrap_socket.return_value = tls
        with patch.object(diagnose.socket, 'create_connection', return_value=raw), patch.object(
            diagnose.ssl, 'create_default_context', return_value=context
        ):
            result = diagnose.probe_imap('imap.example.test')
        context.wrap_socket.assert_called_once_with(raw, server_hostname='imap.example.test')
        tls.sendall.assert_called_once_with(b'a1 CAPABILITY\r\n')
        return result

    def test_normal_response(self):
        self.assertTrue(self.probe(b'* OK ready\r\n* CAPABILITY IMAP4rev1\r\na1 OK done\r\n')['capability_ok'])

    def test_case_insensitive_protocol_keywords(self):
        result = self.probe(b'* ok ready\r\n* capability IMAP4rev1\r\na1 ok done\r\n')
        self.assertTrue(result['capability_ok'])

    def test_preauth_greeting(self):
        self.assertTrue(self.probe(b'* preauth ready\r\n* CAPABILITY IMAP4rev1\r\na1 OK done\r\n')['greeting_ok'])

    def test_missing_capability_is_not_success(self):
        with self.assertRaisesRegex(ConnectionError, 'Missing IMAP CAPABILITY'):
            self.probe(b'* OK ready\r\na1 OK done\r\n')

    def test_empty_capability_is_not_success(self):
        with self.assertRaises(ConnectionError):
            self.probe(b'* OK ready\r\n* CAPABILITY \r\na1 OK done\r\n')

    def test_rejected_command(self):
        with self.assertRaisesRegex(ConnectionError, 'rejected'):
            self.probe(b'* OK ready\r\n* CAPABILITY IMAP4rev1\r\na1 NO denied\r\n')

    def test_tag_is_case_sensitive(self):
        with self.assertRaises(ConnectionError):
            self.probe(b'* OK ready\r\n* CAPABILITY IMAP4rev1\r\nA1 OK done\r\n')

    def test_incomplete_line(self):
        with self.assertRaises(ConnectionError):
            self.probe(b'* OK ready\r\n* CAPABILITY IMAP4rev1\r\na1 OK done')


class ControllerHandler(http.server.BaseHTTPRequestHandler):
    redirect = False
    seen = []
    auth = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        type(self).seen.append(self.path)
        type(self).auth.append(self.headers.get('Authorization'))
        if self.redirect:
            self.send_response(302)
            self.send_header('Location', '/must-not-follow')
            self.end_headers()
            return
        data = {'connections': [
            {'id': 'ipv4', 'metadata': {'destinationIP': '198.18.1.146'}},
            {'id': 'ipv6', 'metadata': {'destinationIP': '2001:0db8:0000:0000:0000:0000:0000:0001'}},
            {'id': 'no-ip', 'metadata': {'destinationIP': ''}},
        ]}
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), ControllerHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = pathlib.Path(self.temp.name) / 'config.json'
        ControllerHandler.redirect = False
        ControllerHandler.seen.clear()
        ControllerHandler.auth.clear()
        self.configure('127.0.0.1:' + str(self.server.server_port))

    def configure(self, endpoint):
        self.config.write_text(json.dumps({'experimental': {'clash_api': {
            'external_controller': endpoint, 'secret': 'test-only',
        }}}))

    def test_authenticated_filter_without_environment_proxy(self):
        with patch.dict('os.environ', {'http_proxy': 'http://192.0.2.1:1'}):
            result = diagnose.connections(self.config, '198.18.1.146')
        self.assertEqual([item['id'] for item in result], ['ipv4'])
        self.assertEqual(ControllerHandler.auth, ['Bearer test-only'])

    def test_equivalent_ipv6(self):
        result = diagnose.connections(self.config, '2001:db8::1')
        self.assertEqual([item['id'] for item in result], ['ipv6'])

    def test_redirect_does_not_forward_credentials(self):
        ControllerHandler.redirect = True
        with self.assertRaises(urllib.error.HTTPError) as caught:
            diagnose.connections(self.config, '198.18.1.146')
        self.assertEqual(caught.exception.code, 302)
        self.assertEqual(ControllerHandler.seen, ['/connections'])

    def test_non_loopback_rejected_before_request(self):
        self.configure('192.0.2.1:80')
        with self.assertRaises(ValueError):
            diagnose.connections(self.config, '198.18.1.146')
        self.assertEqual(ControllerHandler.seen, [])

    def test_error_output_omits_server_text(self):
        error = urllib.error.HTTPError('http://secret.example/', 401, 'private server text', {}, None)
        self.assertEqual(diagnose.error_category(error), 'HTTP 401')

    def test_truncated_socks_reply(self):
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        right.sendall(b'ab')
        right.shutdown(socket.SHUT_WR)
        self.assertEqual(diagnose.exact(left, 2), b'ab')
        with self.assertRaises(ConnectionError):
            diagnose.exact(left, 1)


if __name__ == '__main__':
    unittest.main()
